"""
Schematic Builder для Mindustry 160.7.

Принимает результат конвертации (ConversionResult) и собирает .msch-схему
с дисплеем и N процессорами, содержащими готовый MLOG-код.
Использует pymsch (pip install pymsch).

Формат схемы:
  - 1× дисплей (LOGIC_DISPLAY 3x3 или LARGE_LOGIC_DISPLAY 6x6)
  - N× LOGIC_PROCESSOR (2x2) вокруг дисплея
  - Каждый процессор слинкован с дисплеем через ProcessorLink

Расположение процессоров:
  Если процессоров мало (≤ slots на правой стороне) — правая сторона.
  Иначе — по периметру (право, верх, лево, низ), без перекрытия дисплея.

Link-координаты в pymsch: (block.x − proc.x, block.y − proc.y),
то есть вектор ОТ процессора К дисплею.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from converter import ConversionResult, ProcessorCode

try:
    from pymsch import (
        Block,
        Content,
        ProcessorConfig,
        ProcessorLink,
        Schematic,
    )
    PYMSCH_AVAILABLE = True
except ImportError:
    PYMSCH_AVAILABLE = False


# ─── Конфигурации блоков ───────────────────────────────────────────────────

@dataclass
class _BlockDef:
    """Описание блока для сборки схемы."""
    display_content: Content   # Content.LOGIC_DISPLAY или LARGE_LOGIC_DISPLAY
    display_size: int            # 3 для small, 6 для large
    processor_content: Content # Content.LOGIC_PROCESSOR
    processor_size: int          # 2 для logic-processor


DISPLAY_SMALL_DEF = _BlockDef(
    display_content=None,   # заполняется ниже
    display_size=3,
    processor_content=None,
    processor_size=2,
)

DISPLAY_LARGE_DEF = _BlockDef(
    display_content=None,
    display_size=6,
    processor_content=None,
    processor_size=2,
)


def _get_block_defs() -> tuple[_BlockDef, _BlockDef]:
    """Возвращает конфигурации Small и Large дисплеев с заполненными Content."""
    if not PYMSCH_AVAILABLE:
        raise ImportError("pymsch не установлен. Выполните: pip install pymsch")
    small = _BlockDef(
        display_content=Content.LOGIC_DISPLAY,
        display_size=3,
        processor_content=Content.LOGIC_PROCESSOR,
        processor_size=2,
    )
    large = _BlockDef(
        display_content=Content.LARGE_LOGIC_DISPLAY,
        display_size=6,
        processor_content=Content.LOGIC_PROCESSOR,
        processor_size=2,
    )
    return small, large


# ─── Layout: расстановка процессоров вокруг дисплея ───────────────────────

def _processor_positions(disp_size: int, proc_size: int, n: int) -> list[tuple[int, int]]:
    """
    Возвращает (x, y) центров процессоров вокруг дисплея с центром в (0, 0).

    Координаты рассчитываются строго по границам тайлов pymsch:
      smallest_c = c - (size - 1) // 2
      largest_c  = smallest_c + size - 1

    Процессоры размещаются по 4 сторонам (право, верх, лево, низ),
    а при большом N добавляются дополнительные колонки справа.
    Полностью исключает любые коллизии между процессорами и дисплеем.
    """
    # Границы тайлов дисплея с центром в (0, 0)
    d_min_x = 0 - (disp_size - 1) // 2
    d_max_x = d_min_x + disp_size - 1
    d_min_y = 0 - (disp_size - 1) // 2
    d_max_y = d_min_y + disp_size - 1

    p_offset_lo = (proc_size - 1) // 2
    p_offset_hi = proc_size - 1 - p_offset_lo

    cx_right = d_max_x + 1 + p_offset_lo
    cx_left = d_min_x - 1 - p_offset_hi
    cy_top = d_max_y + 1 + p_offset_lo
    cy_bottom = d_min_y - 1 - p_offset_hi

    slots = disp_size // proc_size
    positions: list[tuple[int, int]] = []

    # Сторона 1: Справа (вдоль Y)
    for i in range(slots):
        positions.append((cx_right, d_min_y + p_offset_lo + i * proc_size))

    # Сторона 2: Сверху (вдоль X)
    for i in range(slots):
        positions.append((d_min_x + p_offset_lo + i * proc_size, cy_top))

    # Сторона 3: Слева (вдоль Y)
    for i in range(slots):
        positions.append((cx_left, d_min_y + p_offset_lo + i * proc_size))

    # Сторона 4: Снизу (вдоль X)
    for i in range(slots):
        positions.append((d_min_x + p_offset_lo + i * proc_size, cy_bottom))

    if len(positions) >= n:
        return positions[:n]

    # Если процессоров больше, чем помещается на 4 сторонах:
    # добавляем параллельные колонки справа
    col = 1
    total_y_slots = max(1, (cy_top - cy_bottom + proc_size) // proc_size)
    while len(positions) < n:
        col_x = cx_right + col * proc_size
        for i in range(total_y_slots):
            positions.append((col_x, cy_bottom + i * proc_size))
            if len(positions) >= n:
                break
        col += 1

    return positions[:n]


# ─── Публичный API ─────────────────────────────────────────────────────────

@dataclass
class SchematicResult:
    """Результат сборки схемы."""
    schematic_base64: str     # base64-строка для импорта в игру (буфер)
    schematic_bytes: bytes    # бинарные данные для сохранения в .msch файл
    block_count: int          # всего блоков в схеме
    processor_count: int      # кол-во процессоров
    display_type: str         # "small" или "large"
    layout_width: int         # ширина схемы в тайлах
    layout_height: int        # высота схемы в тайлах


def build_schematic(
    result: ConversionResult,
    display_key: str = "small",
    display_name: str = "display1",
    schematic_name: str | None = None,
) -> SchematicResult:
    """
    Собирает .msch схему из результата конвертации.

    Args:
        result:        ConversionResult от ConverterService
        display_key:   "small" (80×80) или "large" (176×176)
        display_name:  Имя дисплея в игре (для ProcessorLink и drawflush)
        schematic_name: Название схемы. По умолчанию «Mindcode Image Display»

    Returns:
        SchematicResult с base64 и байтами схемы.
    """
    if not PYMSCH_AVAILABLE:
        raise ImportError(
            "pymsch не установлен. Запустите: pip install pymsch\n"
            "Эта библиотека нужна для генерации .msch схем."
        )

    small_def, large_def = _get_block_defs()
    bdef = large_def if display_key == "large" else small_def

    # Список процессоров
    procs: list[ProcessorCode] = result.processors or []
    if not procs:
        # Одиночный — создаём заглушку
        from converter import ProcessorCode as PC
        procs = [PC(
            index=1,
            name="proc1",
            mindcode=result.mindcode,
            mlog=result.mlog,
            instruction_count=result.estimated_instructions,
            rect_count=len(result.rectangles),
        )]

    n = len(procs)

    # Позиции процессоров (координаты центров)
    proc_positions = _processor_positions(bdef.display_size, bdef.processor_size, n)

    # Дисплей в центре (0, 0)
    disp_x, disp_y = 0, 0

    # Строим схему
    schem = Schematic()
    schem.set_tag("name", schematic_name or "Mindcode Image Display")
    schem.add_label("image")
    schem.add_label("display")

    # Добавляем дисплей
    schem.add_block(Block(bdef.display_content, disp_x, disp_y, None, 0))

    # Добавляем процессоры
    for i, p in enumerate(procs):
        if i >= len(proc_positions):
            break
        px, py = proc_positions[i]
        # Вектор от процессора к дисплею (ProcessorLink: disp.xy − proc.xy)
        link_dx = disp_x - px
        link_dy = disp_y - py
        link = ProcessorLink(link_dx, link_dy, display_name)
        config = ProcessorConfig(p.mlog, [link])
        schem.add_block(Block(bdef.processor_content, px, py, config, 0))

    # Получаем размеры и сериализуем
    w, h = schem.get_dimensions()
    raw_bytes = schem._write()
    b64_str = base64.standard_b64encode(raw_bytes).decode("ascii")

    return SchematicResult(
        schematic_base64=b64_str,
        schematic_bytes=bytes(raw_bytes),
        block_count=len(schem.tiles),
        processor_count=n,
        display_type=display_key,
        layout_width=w,
        layout_height=h,
    )


def save_schematic_file(result: SchematicResult, path: str) -> None:
    """Сохраняет схему в .msch файл."""
    with open(path, "wb") as f:
        f.write(result.schematic_bytes)


def copy_schematic_to_clipboard(result: SchematicResult) -> bool:
    """Копирует base64-строку схемы в буфер обмена (для импорта в Mindustry)."""
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(result.schematic_base64)
        r.update()
        r.destroy()
        return True
    except Exception:  # noqa: BLE001
        try:
            import pyperclip
            pyperclip.copy(result.schematic_base64)
            return True
        except Exception:  # noqa: BLE001
            return False
