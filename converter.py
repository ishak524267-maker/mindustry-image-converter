"""
Mindcode Image Converter - Core Engine
Модуль обработки изображений, 2D Greedy Meshing и компиляции в Mindcode / Mlog для Mindustry 160.7.
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass

from PIL import Image


@dataclass
class DisplayConfig:
    name: str
    width: int
    height: int


DISPLAYS = {
    "small": DisplayConfig("Logic Display", 80, 80),
    "large": DisplayConfig("Large Logic Display", 176, 176),
}


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int
    color_hex: str
    color_rgb: tuple[int, int, int]


@dataclass
class ProcessorCode:
    index: int
    name: str
    mindcode: str
    mlog: str
    instruction_count: int
    rect_count: int


@dataclass
class ConversionResult:
    mindcode: str
    mlog: str
    rectangles: list[Rect]
    bg_color_rgb: tuple[int, int, int]
    bg_color_hex: str
    color_count: int
    estimated_instructions: int
    grid_width: int
    grid_height: int
    display_width: int
    display_height: int
    preview_image: Image.Image
    processors: list[ProcessorCode] = None
    processor_count: int = 1

    def __post_init__(self):
        if self.processors is None:
            self.processors = []
        if self.processors:
            self.processor_count = len(self.processors)
        else:
            self.processor_count = 1


class ImageProcessor:
    """Обрабатывает и квантует исходное изображение."""

    @staticmethod
    def load_and_preprocess(
        image_path: str,
        target_display: DisplayConfig,
        grid_size: tuple[int, int] | None = None,
        aspect_mode: str = "fit",  # "fit", "fill", "stretch"
        num_colors: int = 16,
        dither: bool = False,
    ) -> tuple[Image.Image, tuple[int, int, int], str, int, int, float, float, int, int]:
        img = Image.open(image_path).convert("RGBA")
        
        disp_w = target_display.width
        disp_h = target_display.height
        
        if grid_size is None:
            gw, gh = disp_w, disp_h
        else:
            gw, gh = grid_size

        if gw <= 0 or gh <= 0:
            raise ValueError(f"Размер сетки должен быть положительным (получено {gw}x{gh})")

        scale_x = disp_w / gw
        scale_y = disp_h / gh

        if aspect_mode == "stretch":
            resized = img.resize((gw, gh), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 255))
            canvas.paste(resized, (0, 0), resized)
            offset_x, offset_y = 0, 0
        elif aspect_mode == "fill":
            orig_w, orig_h = img.size
            ratio = max(gw / orig_w, gh / orig_h)
            new_w = int(orig_w * ratio)
            new_h = int(orig_h * ratio)
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            crop_x = (new_w - gw) // 2
            crop_y = (new_h - gh) // 2
            cropped = resized.crop((crop_x, crop_y, crop_x + gw, crop_y + gh))
            canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 255))
            canvas.paste(cropped, (0, 0), cropped)
            offset_x, offset_y = 0, 0
        else:
            # "fit" (сохранение пропорций с центрированием)
            orig_w, orig_h = img.size
            ratio = min(gw / orig_w, gh / orig_h)
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            canvas = Image.new("RGBA", (gw, gh), (0, 0, 0, 255))
            paste_x = (gw - new_w) // 2
            paste_y = (gh - new_h) // 2
            canvas.paste(resized, (paste_x, paste_y), resized)
            offset_x, offset_y = 0, 0

        # Убираем альфа-канал
        final_rgb = Image.new("RGB", (gw, gh), (0, 0, 0))
        final_rgb.paste(canvas, mask=canvas.split()[3])

        # Квантование цветов (палитра)
        dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
        quantized_p = final_rgb.quantize(
            colors=num_colors,
            method=Image.Quantize.MEDIANCUT,
            dither=dither_mode
        )
        
        palette = quantized_p.getpalette()
        color_counts = quantized_p.getcolors()
        
        # Находим самый частый цвет для очистки фона
        dominant_index = max(color_counts, key=lambda item: item[0])[1]
        bg_r = palette[dominant_index * 3]
        bg_g = palette[dominant_index * 3 + 1]
        bg_b = palette[dominant_index * 3 + 2]
        bg_rgb = (bg_r, bg_g, bg_b)
        bg_hex = f"{bg_r:02X}{bg_g:02X}{bg_b:02X}"

        quantized_rgb = quantized_p.convert("RGB")
        return quantized_rgb, bg_rgb, bg_hex, gw, gh, scale_x, scale_y, offset_x, offset_y


class GreedyMesher:
    """2D Greedy Meshing с инверсией координаты Y под Mindustry (Y=0 снизу)."""

    @staticmethod
    def mesh(
        img_rgb: Image.Image,
        bg_rgb: tuple[int, int, int],
        grid_w: int,
        grid_h: int,
        scale_x: float,
        scale_y: float,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> list[Rect]:
        pixels = img_rgb.load()
        visited = [[False for _ in range(grid_w)] for _ in range(grid_h)]
        rectangles: list[Rect] = []

        for y in range(grid_h):
            for x in range(grid_w):
                if visited[y][x]:
                    continue

                col = pixels[x, y]
                # Пропускаем фоновый цвет (он заливается через clear)
                if col == bg_rgb:
                    visited[y][x] = True
                    continue

                # Расширение по горизонтали вправо
                w = 1
                while x + w < grid_w and not visited[y][x + w] and pixels[x + w, y] == col:
                    w += 1

                # Расширение полученной полосы по вертикали вниз
                h = 1
                can_expand_down = True
                while y + h < grid_h and can_expand_down:
                    for row_x in range(x, x + w):
                        if visited[y + h][row_x] or pixels[row_x, y + h] != col:
                            can_expand_down = False
                            break
                    if can_expand_down:
                        h += 1

                for dy in range(h):
                    for dx in range(w):
                        visited[y + dy][x + dx] = True

                # Инверсия Y для Mindustry: y_mind = (grid_h - y - h) * scale_y
                mind_x = round(x * scale_x) + offset_x
                mind_y = round((grid_h - y - h) * scale_y) + offset_y
                mind_w = max(1, round(w * scale_x))
                mind_h = max(1, round(h * scale_y))

                hex_color = f"{col[0]:02X}{col[1]:02X}{col[2]:02X}"
                rectangles.append(Rect(mind_x, mind_y, mind_w, mind_h, hex_color, col))

        return rectangles


class CodeCompiler:
    """Генерирует валидный Mindcode и компилирует в чистый Mlog с поддержкой нарезки по процессорам."""

    @staticmethod
    def generate_processors(
        rectangles: list[Rect],
        bg_rgb: tuple[int, int, int],
        display_name: str = "display1",
        flush_interval: int = 200,
        max_lines_per_proc: int = 950,
        sync_delay: float = 0.25,
        stop_at_end: bool = True,
        instruction_limit: int | None = 1000,
    ) -> list[ProcessorCode]:
        """
        Нарезает отрисовку прямоугольников на несколько процессоров так,
        чтобы каждый процессор укладывался в лимит max_lines_per_proc (по умолчанию 950 строк, жесткий лимит игры 1000).

        Особенности мульти-процессорной графики:
          - Процессор 1 выполняет draw clear (очистку фона).
          - Процессоры 2..N не очищают экран, а делают wait(delay) для безопасной рассинхронизации.
          - Каждый процессор гарантированно завершается drawflush и stop (предотвращает зацикливание).
          - Каждый процессор самостоятельно выставляет цвет перед рисованием своих прямоугольников.
          - Цвет перевыставляется после каждого промежуточного drawflush: цвет —
            глобальное состояние дисплея, и пачки от разных процессоров чередуются.
        """
        color_groups: dict[str, list[Rect]] = {}
        for rect in rectangles:
            if rect.color_hex not in color_groups:
                color_groups[rect.color_hex] = []
            color_groups[rect.color_hex].append(rect)

        sorted_groups = sorted(color_groups.items(), key=lambda item: len(item[1]), reverse=True)

        procs: list[ProcessorCode] = []
        proc_idx = 1

        cur_mlog: list[str] = []
        cur_mc: list[str] = []
        cur_lines = 0
        cur_rects = 0
        cur_buffer = 0
        cur_color_hex: str | None = None

        def start_new_proc():
            nonlocal cur_mlog, cur_mc, cur_lines, cur_rects, cur_buffer, cur_color_hex
            cur_mlog = []
            cur_mc = []
            cur_lines = 0
            cur_rects = 0
            cur_buffer = 0
            cur_color_hex = None

            cur_mc.append("// ========================================================")
            cur_mc.append(f"// Часть {proc_idx}: Процессор #{proc_idx}")
            cur_mc.append(f"// Целевой экран: {display_name}")
            cur_mc.append("// ========================================================")
            cur_mc.append("")
            if instruction_limit is not None and instruction_limit > 0:
                cur_mc.append(f"#set instruction-limit = {instruction_limit};")
            cur_mc.append("#set goal = size;")
            cur_mc.append("")

            if proc_idx == 1:
                cur_mc.append("// 1. Очистка экрана цветом фона (только Процессор 1)")
                cur_mc.append(f"clear({bg_rgb[0]}, {bg_rgb[1]}, {bg_rgb[2]});\n")
                cur_mlog.append(f"draw clear {bg_rgb[0]} {bg_rgb[1]} {bg_rgb[2]} 0 0 0")
                cur_lines += 1
                # draw clear тоже занимает слот буфера отрисовки,
                # иначе для картинки без прямоугольников не будет ни одного drawflush
                cur_buffer = 1
            else:
                delay = round(min(2.5, (proc_idx - 1) * sync_delay), 2)
                cur_mc.append(f"// Задержка {delay}с (ждем очистки экрана Процессором 1)")
                cur_mc.append(f"wait({delay});\n")
                cur_mlog.append(f"wait {delay}")
                cur_lines += 1

        def close_current_proc():
            nonlocal proc_idx, cur_lines, cur_buffer
            if cur_buffer > 0:
                cur_mc.append("\n// Сброс буфера на дисплей")
                cur_mc.append(f"drawflush({display_name});")
                cur_mlog.append(f"drawflush {display_name}")
                cur_lines += 1
                cur_buffer = 0

            if stop_at_end:
                cur_mc.append("// Остановка процессора")
                # stopProcessor() компилируется в mlog-инструкцию stop,
                # тогда как stop() в Mindcode означает ucontrol stop (остановку юнита)
                cur_mc.append("stopProcessor();")
                cur_mlog.append("stop")
                cur_lines += 1

            procs.append(ProcessorCode(
                index=proc_idx,
                name=f"Процессор {proc_idx}",
                mindcode="\n".join(cur_mc),
                mlog="\n".join(cur_mlog),
                instruction_count=cur_lines,
                rect_count=cur_rects
            ))
            proc_idx += 1

        start_new_proc()

        for hex_col, rects in sorted_groups:
            for r in rects:
                # Рассчитываем, сколько строк займет этот прямоугольник, и при
                # необходимости переносим его на новый процессор. Пересчитываем
                # после каждого переноса: на новом процессоре цвет снова не задан.
                while True:
                    needed_lines = 1  # draw rect
                    if cur_color_hex != hex_col:
                        needed_lines += 1  # draw color
                    if cur_buffer + needed_lines >= flush_interval:
                        # drawflush + повторный draw color в начале следующей пачки
                        needed_lines += 2

                    closing_lines = (1 if (cur_buffer + needed_lines) > 0 else 0) + (1 if stop_at_end else 0)

                    if cur_lines + needed_lines + closing_lines <= max_lines_per_proc:
                        break
                    close_current_proc()
                    start_new_proc()

                if cur_color_hex != hex_col:
                    c_rgb = r.color_rgb
                    cur_mc.append(f"\n// Цвет #{hex_col}")
                    cur_mc.append(f"color({c_rgb[0]}, {c_rgb[1]}, {c_rgb[2]}, 255);")
                    cur_mlog.append(f"draw color {c_rgb[0]} {c_rgb[1]} {c_rgb[2]} 255 0 0")
                    cur_lines += 1
                    cur_buffer += 1
                    cur_color_hex = hex_col

                cur_mc.append(f"rect({r.x}, {r.y}, {r.w}, {r.h});")
                cur_mlog.append(f"draw rect {r.x} {r.y} {r.w} {r.h} 0 0")
                cur_lines += 1
                cur_rects += 1
                cur_buffer += 1

                if cur_buffer >= flush_interval:
                    cur_mc.append(f"drawflush({display_name});")
                    cur_mlog.append(f"drawflush {display_name}")
                    cur_lines += 1
                    cur_buffer = 0
                    # Цвет хранится в состоянии самого дисплея, а не в команде.
                    # Другой процессор может успеть выставить свой цвет между
                    # нашими drawflush, поэтому каждая новая пачка обязана
                    # начинаться с draw color, иначе прямоугольники окрасятся
                    # чужим цветом (на белом фоне это выглядит как белые пятна).
                    cur_color_hex = None

        close_current_proc()
        return procs

    @staticmethod
    def generate(
        rectangles: list[Rect],
        bg_rgb: tuple[int, int, int],
        display_name: str = "display1",
        flush_interval: int = 200,
        stop_at_end: bool = True,
        instruction_limit: int | None = 1000,
        split_processors: bool = True,
        max_lines_per_proc: int = 950,
        sync_delay: float = 0.25,
    ) -> tuple[str, str, int, list[ProcessorCode]]:
        """
        Генерирует исходники Mindcode и MLOG с поддержкой разделения по процессорам.
        Возвращает: (mindcode_str, mlog_str, total_instructions, processors)
        """
        if split_processors:
            processors = CodeCompiler.generate_processors(
                rectangles=rectangles,
                bg_rgb=bg_rgb,
                display_name=display_name,
                flush_interval=flush_interval,
                max_lines_per_proc=max_lines_per_proc,
                sync_delay=sync_delay,
                stop_at_end=stop_at_end,
                instruction_limit=instruction_limit,
            )

            if len(processors) == 1:
                return processors[0].mindcode, processors[0].mlog, processors[0].instruction_count, processors

            # Для мульти-процессорного вывода формируем общий обзорный текст
            mc_combined = []
            mlog_combined = []
            total_instructions = 0

            for p in processors:
                total_instructions += p.instruction_count
                sep_mc = f"// {'=' * 58}\n// {p.name.upper()} ({p.instruction_count} строк, {p.rect_count} прямоугольников)\n// {'=' * 58}\n"
                sep_mlog = f"# {'=' * 58}\n# {p.name.upper()} ({p.instruction_count} строк, {p.rect_count} прямоугольников)\n# {'=' * 58}\n"
                mc_combined.append(sep_mc + p.mindcode)
                mlog_combined.append(sep_mlog + p.mlog)

            return "\n\n".join(mc_combined), "\n\n".join(mlog_combined), total_instructions, processors

        # Однопроцессорный режим без нарезки
        color_groups: dict[str, list[Rect]] = {}
        for rect in rectangles:
            if rect.color_hex not in color_groups:
                color_groups[rect.color_hex] = []
            color_groups[rect.color_hex].append(rect)

        sorted_groups = sorted(color_groups.items(), key=lambda item: len(item[1]), reverse=True)

        mc = []
        mc.append("// ========================================================")
        mc.append("// Сгенерировано Mindcode Image Converter для Mindustry 160.7")
        mc.append(f"// Целевой экран: {display_name}")
        mc.append("// ========================================================")
        mc.append("")
        if instruction_limit is not None and instruction_limit > 0:
            mc.append(f"#set instruction-limit = {instruction_limit};")
        mc.append("#set goal = size;")
        mc.append("")
        mc.append("// 1. Очистка экрана цветом фона")
        mc.append(f"clear({bg_rgb[0]}, {bg_rgb[1]}, {bg_rgb[2]});\n")
        mc.append(f"// 2. Отрисовка графических примитивов (Цветов: {len(sorted_groups)}, Прямоугольников: {len(rectangles)})")

        mlog = []
        mlog.append(f"draw clear {bg_rgb[0]} {bg_rgb[1]} {bg_rgb[2]} 0 0 0")

        instruction_count = 1
        # draw clear тоже занимает слот буфера отрисовки
        buffer_counter = 1

        for hex_col, rects in sorted_groups:
            c_rgb = rects[0].color_rgb
            mc.append(f"\n// Цвет #{hex_col} (примитивов: {len(rects)})")
            mc.append(f"color({c_rgb[0]}, {c_rgb[1]}, {c_rgb[2]}, 255);")

            mlog.append(f"draw color {c_rgb[0]} {c_rgb[1]} {c_rgb[2]} 255 0 0")
            instruction_count += 1
            buffer_counter += 1

            for r in rects:
                mc.append(f"rect({r.x}, {r.y}, {r.w}, {r.h});")
                mlog.append(f"draw rect {r.x} {r.y} {r.w} {r.h} 0 0")
                instruction_count += 1
                buffer_counter += 1

                if buffer_counter >= flush_interval:
                    mc.append(f"drawflush({display_name});")
                    mlog.append(f"drawflush {display_name}")
                    instruction_count += 1
                    buffer_counter = 0

        if buffer_counter > 0:
            mc.append("\n// Сброс буфера команд на дисплей")
            mc.append(f"drawflush({display_name});")
            mlog.append(f"drawflush {display_name}")
            instruction_count += 1

        if stop_at_end:
            mc.append("\n// Остановка процессора для предотвращения мерцания")
            # stopProcessor() компилируется в mlog-инструкцию stop,
            # тогда как stop() в Mindcode означает ucontrol stop (остановку юнита)
            mc.append("stopProcessor();")
            mlog.append("stop")
            instruction_count += 1

        single_proc = [ProcessorCode(
            index=1,
            name="Процессор 1",
            mindcode="\n".join(mc),
            mlog="\n".join(mlog),
            instruction_count=instruction_count,
            rect_count=len(rectangles)
        )]

        return "\n".join(mc), "\n".join(mlog), instruction_count, single_proc


class ConverterService:
    """Сервис конвертации с авто-подбором параметров."""

    @classmethod
    def convert(
        cls,
        image_path: str,
        display_key: str = "small",
        grid_size: tuple[int, int] | None = None,
        num_colors: int = 16,
        aspect_mode: str = "fit",
        dither: bool = False,
        display_name: str = "display1",
        instruction_limit: int | None = 1000,
        stop_at_end: bool = True,
        split_processors: bool = True,
        max_lines_per_proc: int = 950,
        sync_delay: float = 0.25,
    ) -> ConversionResult:
        disp = DISPLAYS.get(display_key, DISPLAYS["small"])
        
        quantized_rgb, bg_rgb, bg_hex, gw, gh, sx, sy, ox, oy = ImageProcessor.load_and_preprocess(
            image_path=image_path,
            target_display=disp,
            grid_size=grid_size,
            aspect_mode=aspect_mode,
            num_colors=num_colors,
            dither=dither,
        )

        rectangles = GreedyMesher.mesh(
            img_rgb=quantized_rgb,
            bg_rgb=bg_rgb,
            grid_w=gw,
            grid_h=gh,
            scale_x=sx,
            scale_y=sy,
            offset_x=ox,
            offset_y=oy,
        )

        mindcode_code, mlog_code, instructions, processors = CodeCompiler.generate(
            rectangles=rectangles,
            bg_rgb=bg_rgb,
            display_name=display_name,
            flush_interval=200,
            stop_at_end=stop_at_end,
            instruction_limit=instruction_limit,
            split_processors=split_processors,
            max_lines_per_proc=max_lines_per_proc,
            sync_delay=sync_delay,
        )

        preview = cls.render_preview(disp.width, disp.height, bg_rgb, rectangles)

        return ConversionResult(
            mindcode=mindcode_code,
            mlog=mlog_code,
            rectangles=rectangles,
            bg_color_rgb=bg_rgb,
            bg_color_hex=bg_hex,
            color_count=len({r.color_hex for r in rectangles}) + 1,
            estimated_instructions=instructions,
            grid_width=gw,
            grid_height=gh,
            display_width=disp.width,
            display_height=disp.height,
            preview_image=preview,
            processors=processors,
            processor_count=len(processors),
        )

    @classmethod
    def auto_fit_to_budget(
        cls,
        image_path: str,
        display_key: str = "small",
        max_instructions: int = 950,
        aspect_mode: str = "fit",
        display_name: str = "display1",
    ) -> ConversionResult:
        """Подбирает сетку и палитру так, чтобы ОДИН процессор уложился в max_instructions."""
        disp = DISPLAYS.get(display_key, DISPLAYS["small"])
        base_w, base_h = disp.width, disp.height

        steps = [1.0, 0.8, 0.65, 0.5, 0.4, 0.3, 0.25]
        candidate_resolutions = []
        for step in steps:
            gw = max(16, int(base_w * step))
            gh = max(16, int(base_h * step))
            if (gw, gh) not in candidate_resolutions:
                candidate_resolutions.append((gw, gh))

        candidate_colors = [16, 12, 8, 6, 4, 3, 2]
        best_result: ConversionResult | None = None

        for gw, gh in candidate_resolutions:
            for n_colors in candidate_colors:
                res = cls.convert(
                    image_path=image_path,
                    display_key=display_key,
                    grid_size=(gw, gh),
                    num_colors=n_colors,
                    aspect_mode=aspect_mode,
                    dither=False,
                    display_name=display_name,
                    instruction_limit=1000,
                    # Авто-подгон всегда подбирает параметры под один процессор,
                    # поэтому сравниваем именно однопроцессорный размер кода.
                    split_processors=False,
                )
                if res.estimated_instructions <= max_instructions:
                    return res
                if best_result is None or res.estimated_instructions < best_result.estimated_instructions:
                    best_result = res

        return best_result or cls.convert(
            image_path=image_path,
            display_key=display_key,
            grid_size=(24, 24),
            num_colors=3,
            aspect_mode=aspect_mode,
            display_name=display_name,
            instruction_limit=1000,
            split_processors=False,
        )

    @staticmethod
    def render_preview(
        disp_w: int,
        disp_h: int,
        bg_rgb: tuple[int, int, int],
        rectangles: list[Rect]
    ) -> Image.Image:
        img = Image.new("RGB", (disp_w, disp_h), bg_rgb)
        pixels = img.load()

        for r in rectangles:
            col = r.color_rgb
            y_start = disp_h - r.y - r.h
            for py in range(max(0, y_start), min(disp_h, y_start + r.h)):
                for px in range(max(0, r.x), min(disp_w, r.x + r.w)):
                    pixels[px, py] = col

        return img

    @staticmethod
    def compile_with_external_jar(mindcode_source: str, jar_path: str = "mindcode.jar") -> tuple[bool, str]:
        """Компилирует через внешний официальный mindcode.jar, если он присутствует."""
        if not os.path.exists(jar_path):
            return False, f"Файл {jar_path} не найден!"

        with tempfile.NamedTemporaryFile("w", suffix=".mnd", delete=False, encoding="utf-8") as f_in:
            f_in.write(mindcode_source)
            temp_in = f_in.name

        temp_out = temp_in + ".mlog"

        try:
            cmd = ["java", "-jar", jar_path, "cm", temp_in, "-o", temp_out]
            res = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=15)
            if res.returncode == 0 and os.path.exists(temp_out):
                with open(temp_out, "r", encoding="utf-8") as f_out:
                    compiled_mlog = f_out.read()
                return True, compiled_mlog
            else:
                return False, f"Ошибка компиляции jar:\n{res.stderr or res.stdout}"
        except Exception as e:  # noqa: BLE001
            return False, str(e)
        finally:
            if os.path.exists(temp_in):
                os.remove(temp_in)
            if os.path.exists(temp_out):
                os.remove(temp_out)
