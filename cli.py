"""
Mindcode Image Converter - Command Line Interface (CLI)
Использование:
  python cli.py <image_path> [опции]

Примеры:
  python cli.py my_icon.png --copy           # Один процессор, скопировать mlog
  python cli.py photo.jpg --split -o out     # Нарезка: out_proc1.mlog, out_proc2.mlog, ...
  python cli.py art.png --auto-fit --copy    # Авто-подгон под 1000 строк
"""

import argparse
import sys
import os
from converter import ConverterService, DISPLAYS


def configure_console():
    """Включает UTF-8 для вывода, чтобы символы ×, ✔, ✖ не роняли CLI на Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def copy_to_clipboard(text: str) -> bool:
    try:
        import tkinter as tk
        r = tk.Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True
    except Exception:
        return False


def main():
    configure_console()

    parser = argparse.ArgumentParser(
        description="Конвертер растровых изображений в Mindcode и MLOG для процессоров Mindustry 160.7."
    )
    parser.add_argument("image", help="Путь к исходному изображению (PNG, JPG, BMP, WEBP)")
    parser.add_argument("-o", "--output",
                        help="Имя или путь выходного файла (без расширения или .mlog/.mnd)")
    parser.add_argument("-d", "--display", choices=["small", "large"], default="small",
                        help="Тип дисплея: small (80×80) или large (176×176). По умолчанию: small")
    parser.add_argument("-c", "--colors", type=int, default=16,
                        help="Количество цветов (2–64). По умолчанию: 16")
    parser.add_argument("-m", "--mode", choices=["fit", "fill", "stretch"], default="fit",
                        help="Режим кадрирования. По умолчанию: fit")
    parser.add_argument("--grid", type=str, default=None,
                        help="Кастомное разрешение сетки, например 40x40")
    parser.add_argument("--dither", action="store_true",
                        help="Включить дизеринг Флойда-Стейнберга")
    parser.add_argument("--auto-fit", action="store_true",
                        help="Автоматический подбор под лимит 1000 строк")
    parser.add_argument("--target", default="display1",
                        help="Имя блока дисплея в игре (по умолчанию: display1)")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Лимит инструкций. 0 = без лимита (World Processor)")
    parser.add_argument("--split", action="store_true",
                        help="Нарезать код на несколько процессоров по ≤950 строк каждый")
    parser.add_argument("--preview", help="Путь для сохранения PNG-превью")
    parser.add_argument("--copy", action="store_true",
                        help="Скопировать MLOG первого (или единственного) процессора в буфер обмена")

    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"Ошибка: Файл '{args.image}' не найден!", file=sys.stderr)
        sys.exit(1)

    if not 2 <= args.colors <= 64:
        print("Ошибка: Количество цветов должно быть в диапазоне 2–64.", file=sys.stderr)
        sys.exit(1)

    grid_size = None
    if args.grid:
        try:
            gw, gh = map(int, args.grid.lower().split("x"))
            grid_size = (gw, gh)
        except Exception:
            print("Ошибка: Параметр --grid должен быть формата WxH (например: 40x40)", file=sys.stderr)
            sys.exit(1)
        if gw <= 0 or gh <= 0:
            print("Ошибка: Ширина и высота --grid должны быть положительными.", file=sys.stderr)
            sys.exit(1)

    print(f"Обработка изображения: {args.image}")

    try:
        if args.auto_fit:
            print("Подбор параметров под лимит 1000 строк...")
            result = ConverterService.auto_fit_to_budget(
                image_path=args.image,
                display_key=args.display,
                max_instructions=950,
                aspect_mode=args.mode,
                display_name=args.target,
            )
        else:
            result = ConverterService.convert(
                image_path=args.image,
                display_key=args.display,
                grid_size=grid_size,
                num_colors=args.colors,
                aspect_mode=args.mode,
                dither=args.dither,
                display_name=args.target,
                instruction_limit=args.limit if args.limit > 0 else None,
                stop_at_end=True,
                split_processors=args.split,
            )
    except (OSError, ValueError) as e:
        print(f"Ошибка обработки изображения: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Вывод статистики ─────────────────────────────────────────────────────
    procs = result.processors or []
    n_procs = len(procs)

    print("\n--- Результаты компиляции ---")
    print(f"Экран: {DISPLAYS[args.display].name} ({result.display_width}×{result.display_height})")
    print(f"Сетка отрисовки: {result.grid_width}×{result.grid_height}")
    print(f"Цветов: {result.color_count}  |  Фон: #{result.bg_color_hex}")
    print(f"Прямоугольников: {len(result.rectangles)}")

    if n_procs > 1:
        print(f"\033[95mПроцессоров: {n_procs}\033[0m")
        for p in procs:
            ok = "\033[92m✔\033[0m" if p.instruction_count <= 1000 else "\033[91m✖\033[0m"
            print(f"  {ok} Процессор {p.index}: {p.instruction_count} строк, {p.rect_count} прямоугольников")
    else:
        inst = result.estimated_instructions
        color = "\033[92m" if inst <= 1000 else "\033[91m"
        print(f"Инструкций mlog: {color}{inst}\033[0m / 1000")

    # ── Определяем базовое имя файла ─────────────────────────────────────────
    if args.output:
        base, ext = os.path.splitext(args.output)
        if ext.lower() in (".mlog", ".mnd"):
            base_path = base
        else:
            base_path = args.output
    else:
        base_path = os.path.splitext(args.image)[0]

    # ── Сохранение файлов ────────────────────────────────────────────────────
    if n_procs > 1:
        # Мульти-процессорный режим: сохраняем по одному файлу на процессор
        for p in procs:
            mlog_path = f"{base_path}_proc{p.index}.mlog"
            mnd_path  = f"{base_path}_proc{p.index}.mnd"
            with open(mlog_path, "w", encoding="utf-8") as f:
                f.write(p.mlog)
            with open(mnd_path, "w", encoding="utf-8") as f:
                f.write(p.mindcode)
            print(f"[OK] Процессор {p.index}: {mlog_path}")

        print(f"\n\033[95m[!] Загрузите файлы в {n_procs} процессоров строго в порядке нумерации!\033[0m")
        print(f"\033[95m[!] Первый процессор рисует фон и запускается первым.\033[0m")
    else:
        # Одиночный режим
        mlog_path = f"{base_path}.mlog"
        mnd_path  = f"{base_path}.mnd"
        with open(mlog_path, "w", encoding="utf-8") as f:
            f.write(result.mlog)
        with open(mnd_path, "w", encoding="utf-8") as f:
            f.write(result.mindcode)
        print(f"\n[OK] Mindcode: {mnd_path}")
        print(f"[OK] MLOG (для процессора): {mlog_path}")

    # ── Превью ───────────────────────────────────────────────────────────────
    if args.preview:
        result.preview_image.save(args.preview)
        print(f"[OK] Превью сохранено: {args.preview}")

    # ── Копирование в буфер ──────────────────────────────────────────────────
    if args.copy:
        mlog_to_copy = procs[0].mlog if procs else result.mlog
        if copy_to_clipboard(mlog_to_copy):
            label = "Процессора 1" if n_procs > 1 else "MLOG"
            print(f"\n[✔] Код {label} скопирован в буфер обмена!")
            if n_procs > 1:
                print(f"    Не забудьте скопировать и загрузить оставшиеся {n_procs - 1} процессора.")
        else:
            print("Предупреждение: Не удалось скопировать в буфер обмена.")


if __name__ == "__main__":
    main()
