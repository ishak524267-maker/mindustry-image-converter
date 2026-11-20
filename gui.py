"""Mindcode Image Converter - Graphic User Interface (GUI).

Современный минималистичный интерфейс на чистом Tkinter для Mindustry 160.7.
Включает встроенную компиляцию в MLOG для прямой вставки в игровой процессор.
Поддерживает нарезку кода на несколько процессоров для сложных изображений.
"""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from converter import ConversionResult, ConverterService, ProcessorCode

# ─── Цветовая палитра: Modern Dark ───────────────────────────────────────────
C_BG_ROOT = "#0f0f12"
C_BG_CARD = "#18181c"
C_BG_INPUT = "#222228"
C_BORDER = "#2b2b32"
C_TEXT_PRIMARY = "#ffffff"
C_TEXT_MUTED = "#9e9ea8"

C_ACCENT_BLUE = "#3b82f6"
C_ACCENT_BLUE_HVR = "#2563eb"
C_ACCENT_GREEN = "#10b981"
C_ACCENT_GREEN_HVR = "#059669"
C_ACCENT_ORANGE = "#f59e0b"
C_ACCENT_ORANGE_HVR = "#d97706"

C_BADGE_OK_BG = "#064e3b"
C_BADGE_OK_FG = "#34d399"
C_BADGE_ERR_BG = "#7f1d1d"
C_BADGE_ERR_FG = "#f87171"
C_BADGE_INFO_BG = "#1e3a5f"
C_BADGE_INFO_FG = "#60a5fa"
C_BADGE_MULTI_BG = "#3b1f5e"
C_BADGE_MULTI_FG = "#c084fc"


class ModernButton(tk.Button):
    def __init__(self, master, bg=C_BG_INPUT, fg=C_TEXT_PRIMARY, hvr_bg="#2c2c34", **kwargs):
        super().__init__(
            master,
            bg=bg,
            fg=fg,
            activebackground=hvr_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
            **kwargs,
        )
        self.default_bg = bg
        self.hvr_bg = hvr_bg
        self.bind("<Enter>", lambda _e: self.configure(bg=self.hvr_bg))
        self.bind("<Leave>", lambda _e: self.configure(bg=self.default_bg))

    def set_color(self, bg: str, hvr_bg: str):
        self.default_bg = bg
        self.hvr_bg = hvr_bg
        self.configure(bg=bg, activebackground=hvr_bg)


class SegmentedControl(tk.Frame):
    def __init__(self, master, options, default_value, on_change=None):
        super().__init__(
            master,
            bg=C_BG_INPUT,
            padx=2,
            pady=2,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        self.on_change = on_change
        self.current_value = default_value
        self.buttons = {}

        for val, label in options:
            btn = tk.Button(
                self,
                text=label,
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=4,
                command=lambda v=val: self.select(v),
            )
            btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1)
            self.buttons[val] = btn

        self._update_appearance()

    def select(self, value):
        if self.current_value != value:
            self.current_value = value
            self._update_appearance()
            if self.on_change:
                self.on_change(value)

    def _update_appearance(self):
        for val, btn in self.buttons.items():
            if val == self.current_value:
                btn.configure(
                    bg=C_ACCENT_BLUE,
                    fg="#ffffff",
                    activebackground=C_ACCENT_BLUE_HVR,
                    activeforeground="#ffffff",
                )
            else:
                btn.configure(
                    bg=C_BG_INPUT,
                    fg=C_TEXT_MUTED,
                    activebackground="#2c2c34",
                    activeforeground=C_TEXT_PRIMARY,
                )

    def get(self):
        return self.current_value


class AppGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Mindcode Image Converter — Mindustry 160.7")
        self.geometry("1200x780")
        self.minsize(1000, 660)
        self.configure(bg=C_BG_ROOT)

        # ── Состояние ────────────────────────────────────────────────────────
        self.current_image_path: str | None = None
        self.current_result: ConversionResult | None = None
        self.tk_orig_image: ImageTk.PhotoImage | None = None
        self.tk_preview_image: ImageTk.PhotoImage | None = None

        self.display_mode = "small"
        self.processor_mode = "multi"   # "multi" | "single" | "world"
        self.aspect_mode = "fit"
        self.num_colors = 12
        self.dither = False
        self.current_tab = "preview"    # "preview" | "mlog" | "mindcode"

        # Индекс выбранного процессора (0..N-1 или -1 для "Все вместе")
        self.selected_proc_idx = 0

        self._build_layout()

    # ─────────────────────────────────────────────────────────────────────────
    # Построение интерфейса
    # ─────────────────────────────────────────────────────────────────────────

    def _build_layout(self):
        # 1. Хедер
        header = tk.Frame(
            self,
            bg=C_BG_CARD,
            padx=16,
            pady=10,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        header.pack(fill=tk.X, side=tk.TOP)

        tk.Label(
            header,
            text="Mindcode Image Converter",
            font=("Segoe UI", 12, "bold"),
            fg=C_TEXT_PRIMARY,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT)

        tk.Label(
            header,
            text="генератор и компилятор графики для Mindustry release build 160.7",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT, padx=(10, 0), pady=(2, 0))

        tk.Label(
            header,
            text="v160.7 | Multi-Proc Ready",
            font=("Segoe UI", 8, "bold"),
            fg="#34d399",
            bg="#064e3b",
            padx=8,
            pady=3,
        ).pack(side=tk.RIGHT)

        # 2. Футер (строим раньше тела, чтобы pack(BOTTOM) работал надежно)
        self.footer = tk.Frame(
            self,
            bg=C_BG_CARD,
            padx=14,
            pady=8,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        self.footer.pack(fill=tk.X, side=tk.BOTTOM)
        self._build_footer()

        # 3. Тело приложения
        body = tk.Frame(self, bg=C_BG_ROOT, padx=10, pady=10)
        body.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(body, bg=C_BG_ROOT, width=320)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)

        self.main_area = tk.Frame(body, bg=C_BG_ROOT)
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self._build_sidebar(sidebar)
        self._build_main_area()

    def _build_sidebar(self, parent):
        # ── Карточка: Изображение ────────────────────────────────────────────
        card_file = self._create_card(parent, "ИЗОБРАЖЕНИЕ")
        ModernButton(
            card_file,
            text="📂 Загрузить файл...",
            bg=C_ACCENT_BLUE,
            hvr_bg=C_ACCENT_BLUE_HVR,
            command=self._on_select_file,
        ).pack(fill=tk.X, pady=(0, 6))

        self.lbl_file_name = tk.Label(
            card_file,
            text="Файл не выбран",
            font=("Segoe UI", 8),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
            wraplength=280,
            justify=tk.LEFT,
        )
        self.lbl_file_name.pack(anchor="w")

        # ── Карточка: Mindustry параметры ────────────────────────────────────
        card_mind = self._create_card(parent, "MINDUSTRY ПАРАМЕТРЫ")

        self._create_field_label(card_mind, "Тип экрана:")
        self.seg_display = SegmentedControl(
            card_mind,
            [("small", "80×80 (Logic)"), ("large", "176×176 (Large)")],
            "small",
            on_change=self._on_display_changed,
        )
        self.seg_display.pack(fill=tk.X, pady=(0, 8))

        self._create_field_label(card_mind, "Режим процессора:")
        self.seg_proc = SegmentedControl(
            card_mind,
            [("multi", "Мульти-проц"), ("single", "1 проц (≤1000)"), ("world", "World")],
            "multi",
            on_change=self._on_proc_changed,
        )
        self.seg_proc.pack(fill=tk.X, pady=(0, 8))

        row_name = tk.Frame(card_mind, bg=C_BG_CARD)
        row_name.pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            row_name,
            text="Имя дисплея в игре:",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT)

        self.entry_target = tk.Entry(
            row_name,
            bg=C_BG_INPUT,
            fg=C_TEXT_PRIMARY,
            insertbackground=C_TEXT_PRIMARY,
            relief="flat",
            font=("Segoe UI", 9),
            highlightthickness=1,
            highlightbackground=C_BORDER,
            width=10,
            justify=tk.CENTER,
        )
        self.entry_target.insert(0, "display1")
        self.entry_target.pack(side=tk.RIGHT)

        self.watchdog_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            card_mind,
            text="Авто-восстановление (Watchdog)",
            variable=self.watchdog_var,
            bg=C_BG_CARD,
            fg=C_TEXT_PRIMARY,
            selectcolor=C_BG_INPUT,
            activebackground=C_BG_CARD,
            activeforeground=C_TEXT_PRIMARY,
            highlightthickness=0,
            font=("Segoe UI", 9),
            command=self._on_watchdog_toggle,
        ).pack(anchor="w", pady=(6, 2))

        # ── Карточка: Графика и сжатие ───────────────────────────────────────
        card_gfx = self._create_card(parent, "ГРАФИКА И СЖАТИЕ")

        self._create_field_label(card_gfx, "Масштабирование:")
        self.seg_aspect = SegmentedControl(
            card_gfx,
            [("fit", "Вписать"), ("fill", "Заполнить"), ("stretch", "Растянуть")],
            "fit",
            on_change=self._on_aspect_changed,
        )
        self.seg_aspect.pack(fill=tk.X, pady=(0, 8))

        row_slider_head = tk.Frame(card_gfx, bg=C_BG_CARD)
        row_slider_head.pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            row_slider_head,
            text="Цветов в палитре:",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT)
        self.lbl_colors_val = tk.Label(
            row_slider_head,
            text="12",
            font=("Segoe UI", 9, "bold"),
            fg=C_ACCENT_BLUE,
            bg=C_BG_CARD,
        )
        self.lbl_colors_val.pack(side=tk.RIGHT)

        self.slider_colors = tk.Scale(
            card_gfx,
            from_=2,
            to=32,
            orient=tk.HORIZONTAL,
            bg=C_BG_CARD,
            fg=C_TEXT_PRIMARY,
            troughcolor=C_BG_INPUT,
            highlightthickness=0,
            bd=0,
            activebackground=C_ACCENT_BLUE,
            showvalue=False,
            command=self._on_slider_change,
        )
        self.slider_colors.set(12)
        self.slider_colors.pack(fill=tk.X, pady=(0, 8))

        self.dither_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            card_gfx,
            text="Сглаживание (Floyd-Steinberg)",
            variable=self.dither_var,
            bg=C_BG_CARD,
            fg=C_TEXT_PRIMARY,
            selectcolor=C_BG_INPUT,
            activebackground=C_BG_CARD,
            activeforeground=C_TEXT_PRIMARY,
            highlightthickness=0,
            font=("Segoe UI", 9),
            command=self._on_dither_toggle,
        ).pack(anchor="w", pady=(0, 4))

        # ── Кнопки действий ──────────────────────────────────────────────────
        ModernButton(
            parent,
            text="🚀 Авто-подгон под 1000 строк",
            bg=C_ACCENT_GREEN,
            hvr_bg=C_ACCENT_GREEN_HVR,
            command=self._on_auto_fit,
        ).pack(fill=tk.X, pady=(0, 6))

        ModernButton(
            parent,
            text="⚡ Пересчитать",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._run_conversion,
        ).pack(fill=tk.X)

    def _build_main_area(self):
        # ── Таб-бар ──────────────────────────────────────────────────────────
        tab_bar = tk.Frame(self.main_area, bg=C_BG_ROOT)
        tab_bar.pack(fill=tk.X, pady=(0, 8))

        self.btn_tab_prev = ModernButton(
            tab_bar,
            text="🖼️ Предпросмотр",
            bg=C_ACCENT_BLUE,
            hvr_bg=C_ACCENT_BLUE_HVR,
            command=lambda: self._switch_tab("preview"),
        )
        self.btn_tab_prev.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tab_mlog = ModernButton(
            tab_bar,
            text="⚡ MLOG (в процессор)",
            bg=C_BG_CARD,
            hvr_bg="#24242c",
            fg=C_TEXT_MUTED,
            command=lambda: self._switch_tab("mlog"),
        )
        self.btn_tab_mlog.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_tab_mind = ModernButton(
            tab_bar,
            text="📜 Mindcode (.mnd)",
            bg=C_BG_CARD,
            hvr_bg="#24242c",
            fg=C_TEXT_MUTED,
            command=lambda: self._switch_tab("mindcode"),
        )
        self.btn_tab_mind.pack(side=tk.LEFT)

        self.btn_tab_schem = ModernButton(
            tab_bar,
            text="📦 Схема (.msch)",
            bg=C_BG_CARD,
            hvr_bg="#24242c",
            fg=C_TEXT_MUTED,
            command=lambda: self._switch_tab("schematic"),
        )
        self.btn_tab_schem.pack(side=tk.LEFT, padx=(6, 0))

        # ── Контейнер вкладок ────────────────────────────────────────────────
        self.view_container = tk.Frame(
            self.main_area,
            bg=C_BG_CARD,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        self.view_container.pack(fill=tk.BOTH, expand=True)

        # Вкладка 1: Предпросмотр
        self.frame_preview = tk.Frame(self.view_container, bg=C_BG_CARD, padx=12, pady=12)

        box_left = tk.Frame(
            self.frame_preview,
            bg=C_BG_ROOT,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        box_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        tk.Label(
            box_left,
            text="Исходное изображение",
            font=("Segoe UI", 9, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_ROOT,
            pady=6,
        ).pack(side=tk.TOP, fill=tk.X)
        self.canvas_orig = tk.Canvas(box_left, bg="#121216", highlightthickness=0)
        self.canvas_orig.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        box_right = tk.Frame(
            self.frame_preview,
            bg=C_BG_ROOT,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        box_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        tk.Label(
            box_right,
            text="Экран в Mindustry (пиксельный вид)",
            font=("Segoe UI", 9, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_ROOT,
            pady=6,
        ).pack(side=tk.TOP, fill=tk.X)
        self.canvas_disp = tk.Canvas(box_right, bg="#121216", highlightthickness=0)
        self.canvas_disp.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

        # Вкладка 2: MLOG
        self.frame_mlog = tk.Frame(self.view_container, bg=C_BG_CARD, padx=10, pady=10)

        mlog_top = tk.Frame(self.frame_mlog, bg=C_BG_CARD)
        mlog_top.pack(fill=tk.X, pady=(0, 4))
        self.lbl_mlog_hint = tk.Label(
            mlog_top,
            text="Вставьте этот код в процессор через «Вставить из буфера» (Ctrl+V)",
            font=("Segoe UI", 8),
            fg="#34d399",
            bg=C_BG_CARD,
        )
        self.lbl_mlog_hint.pack(side=tk.LEFT, anchor="w")

        self.proc_tab_bar_mlog = tk.Frame(self.frame_mlog, bg=C_BG_CARD)
        self.proc_tab_bar_mlog.pack(fill=tk.X, pady=(0, 4))
        self.text_mlog = self._create_text_editor(self.frame_mlog)

        # Вкладка 3: Mindcode
        self.frame_mindcode = tk.Frame(self.view_container, bg=C_BG_CARD, padx=10, pady=10)

        mind_top = tk.Frame(self.frame_mindcode, bg=C_BG_CARD)
        mind_top.pack(fill=tk.X, pady=(0, 4))
        self.lbl_mind_hint = tk.Label(
            mind_top,
            text="Исходный код на языке Mindcode (валидный синтаксис: clear, color, rect, drawflush, stop)",
            font=("Segoe UI", 8),
            fg="#60a5fa",
            bg=C_BG_CARD,
        )
        self.lbl_mind_hint.pack(side=tk.LEFT, anchor="w")

        self.proc_tab_bar_mind = tk.Frame(self.frame_mindcode, bg=C_BG_CARD)
        self.proc_tab_bar_mind.pack(fill=tk.X, pady=(0, 4))
        self.text_mindcode = self._create_text_editor(self.frame_mindcode)

        # Вкладка 4: Схема (.msch)
        self.frame_schematic = tk.Frame(self.view_container, bg=C_BG_CARD, padx=10, pady=10)

        schem_top = tk.Frame(self.frame_schematic, bg=C_BG_CARD)
        schem_top.pack(fill=tk.X, pady=(0, 4))
        self.lbl_schem_hint = tk.Label(
            schem_top,
            text="Готовая схема Mindustry: дисплей + все процессоры с предзагруженным MLOG кодом и связями",
            font=("Segoe UI", 8),
            fg="#c084fc",
            bg=C_BG_CARD,
        )
        self.lbl_schem_hint.pack(side=tk.LEFT, anchor="w")

        schem_action_bar = tk.Frame(self.frame_schematic, bg=C_BG_CARD)
        schem_action_bar.pack(fill=tk.X, pady=(0, 6))

        self.btn_schem_tab_copy = ModernButton(
            schem_action_bar,
            text="📦 Скопировать схему в буфер",
            bg=C_ACCENT_ORANGE,
            hvr_bg=C_ACCENT_ORANGE_HVR,
            command=self._on_copy_schematic,
        )
        self.btn_schem_tab_copy.pack(side=tk.LEFT, padx=(0, 6))

        ModernButton(
            schem_action_bar,
            text="💾 Сохранить .msch файл",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._on_save_schematic,
        ).pack(side=tk.LEFT)

        self.lbl_schem_info = tk.Label(
            schem_action_bar,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg=C_TEXT_PRIMARY,
            bg=C_BG_CARD,
        )
        self.lbl_schem_info.pack(side=tk.RIGHT)

        self.text_schematic = self._create_text_editor(self.frame_schematic)

        self.frame_preview.pack(fill=tk.BOTH, expand=True)

    def _create_text_editor(self, parent):
        container = tk.Frame(parent, bg=C_BG_CARD)
        container.pack(fill=tk.BOTH, expand=True)

        txt = tk.Text(
            container,
            bg="#111115",
            fg="#e4e4e7",
            insertbackground="#ffffff",
            font=("Consolas", 10),
            relief="flat",
            bd=0,
            wrap=tk.NONE,
        )
        scroll_y = tk.Scrollbar(container, orient=tk.VERTICAL, command=txt.yview)
        scroll_x = tk.Scrollbar(container, orient=tk.HORIZONTAL, command=txt.xview)
        txt.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return txt

    def _build_footer(self):
        left_box = tk.Frame(self.footer, bg=C_BG_CARD)
        left_box.pack(side=tk.LEFT, fill=tk.Y)

        self.badge_status = tk.Label(
            left_box,
            text="Инструкций: — / 1000",
            font=("Segoe UI", 9, "bold"),
            bg=C_BG_INPUT,
            fg=C_TEXT_MUTED,
            padx=10,
            pady=4,
        )
        self.badge_status.pack(side=tk.LEFT, padx=(0, 10))

        self.lbl_details = tk.Label(
            left_box,
            text="Загрузите изображение для начала",
            font=("Segoe UI", 9),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        )
        self.lbl_details.pack(side=tk.LEFT)

        right_box = tk.Frame(self.footer, bg=C_BG_CARD)
        right_box.pack(side=tk.RIGHT)

        self.btn_save_mlog = ModernButton(
            right_box,
            text="💾 Сохранить .mlog",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._on_save_mlog,
        )
        self.btn_save_mlog.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_copy_mind = ModernButton(
            right_box,
            text="📋 Скопировать Mindcode",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._on_copy_mindcode,
        )
        self.btn_copy_mind.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_copy_mlog = ModernButton(
            right_box,
            text="⚡ Скопировать MLOG (для игры)",
            bg=C_ACCENT_GREEN,
            hvr_bg=C_ACCENT_GREEN_HVR,
            command=self._on_copy_mlog,
        )
        self.btn_copy_mlog.pack(side=tk.LEFT)

        self.btn_copy_schematic = ModernButton(
            right_box,
            text="📦 Скопировать схему (.msch)",
            bg=C_ACCENT_ORANGE,
            hvr_bg=C_ACCENT_ORANGE_HVR,
            command=self._on_copy_schematic,
        )
        self.btn_copy_schematic.pack(side=tk.LEFT, padx=(6, 0))

        self.btn_save_schematic = ModernButton(
            right_box,
            text="💾 Сохранить .msch",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._on_save_schematic,
        )
        self.btn_save_schematic.pack(side=tk.LEFT, padx=(6, 0))

        self.btn_next_proc = ModernButton(
            right_box,
            text="▶ След. (#2)",
            bg=C_BG_INPUT,
            hvr_bg="#2c2c34",
            command=self._on_next_proc,
        )
        # По умолчанию скрыта, отображается при наличии следующего процессора
        self.btn_next_proc.pack_forget()

    def _create_card(self, parent, title):
        card = tk.Frame(
            parent,
            bg=C_BG_CARD,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=C_BORDER,
        )
        card.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            card,
            text=title,
            font=("Segoe UI", 8, "bold"),
            fg="#60a5fa",
            bg=C_BG_CARD,
        ).pack(anchor="w", pady=(0, 6))
        return card

    def _create_field_label(self, parent, text):
        lbl = tk.Label(parent, text=text, font=("Segoe UI", 9), fg=C_TEXT_MUTED, bg=C_BG_CARD)
        lbl.pack(anchor="w", pady=(0, 2))
        return lbl

    # ─────────────────────────────────────────────────────────────────────────
    # Кнопки выбора процессора (мульти-процессор)
    # ─────────────────────────────────────────────────────────────────────────

    def _rebuild_proc_tabs(self, processors: list[ProcessorCode]):
        """Перестраивает кнопки выбора процессоров в MLOG и Mindcode."""
        for widget in self.proc_tab_bar_mlog.winfo_children():
            widget.destroy()
        for widget in self.proc_tab_bar_mind.winfo_children():
            widget.destroy()

        n = len(processors)
        if n <= 1:
            self.proc_tab_bar_mlog.pack_forget()
            self.proc_tab_bar_mind.pack_forget()
            if hasattr(self, "btn_next_proc"):
                self.btn_next_proc.pack_forget()
            if hasattr(self, "btn_copy_mlog"):
                self.btn_copy_mlog.configure(text="⚡ Скопировать MLOG (для игры)")
            return

        self.proc_tab_bar_mlog.pack(fill=tk.X, pady=(0, 4))
        self.proc_tab_bar_mind.pack(fill=tk.X, pady=(0, 4))

        tk.Label(
            self.proc_tab_bar_mlog,
            text="Процессор:",
            font=("Segoe UI", 8, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(
            self.proc_tab_bar_mind,
            text="Процессор:",
            font=("Segoe UI", 8, "bold"),
            fg=C_TEXT_MUTED,
            bg=C_BG_CARD,
        ).pack(side=tk.LEFT, padx=(0, 6))

        for p in processors:
            idx = p.index - 1
            btn_mlog = tk.Button(
                self.proc_tab_bar_mlog,
                text=f"#{p.index} ({p.instruction_count} стр)",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=6,
                pady=3,
                command=lambda i=idx: self._select_proc(i),
            )
            btn_mlog.pack(side=tk.LEFT, padx=(0, 4))

            btn_mind = tk.Button(
                self.proc_tab_bar_mind,
                text=f"#{p.index} ({p.instruction_count} стр)",
                relief="flat",
                bd=0,
                cursor="hand2",
                font=("Segoe UI", 8, "bold"),
                padx=6,
                pady=3,
                command=lambda i=idx: self._select_proc(i),
            )
            btn_mind.pack(side=tk.LEFT, padx=(0, 4))

        # Кнопка «Все вместе» (-1)
        btn_all_mlog = tk.Button(
            self.proc_tab_bar_mlog,
            text="Все вместе",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=3,
            command=lambda: self._select_proc(-1),
        )
        btn_all_mlog.pack(side=tk.LEFT, padx=(4, 0))

        btn_all_mind = tk.Button(
            self.proc_tab_bar_mind,
            text="Все вместе",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
            padx=6,
            pady=3,
            command=lambda: self._select_proc(-1),
        )
        btn_all_mind.pack(side=tk.LEFT, padx=(4, 0))

        self._update_proc_tab_colors()

    def _update_proc_tab_colors(self):
        """Подсвечивает выбранный процессор в панелях переключения."""
        for bar in (self.proc_tab_bar_mlog, self.proc_tab_bar_mind):
            buttons = [w for w in bar.winfo_children() if isinstance(w, tk.Button)]
            # Последняя кнопка — «Все вместе» (соответствует idx == -1)
            for i, btn in enumerate(buttons):
                is_selected = (
                    (self.selected_proc_idx == -1 and i == len(buttons) - 1)
                    or (self.selected_proc_idx == i)
                )
                if is_selected:
                    btn.configure(
                        bg=C_ACCENT_ORANGE,
                        fg="#ffffff",
                        activebackground=C_ACCENT_ORANGE_HVR,
                    )
                else:
                    btn.configure(
                        bg=C_BG_INPUT,
                        fg=C_TEXT_MUTED,
                        activebackground="#2c2c34",
                    )

    def _select_proc(self, idx: int):
        """Переключает отображение на конкретный процессор или объединенный код."""
        if not self.current_result:
            return
        procs = self.current_result.processors or []
        n = len(procs)

        if idx != -1 and (idx < 0 or idx >= n):
            return

        self.selected_proc_idx = idx
        self._update_proc_tab_colors()

        self.text_mlog.delete("1.0", tk.END)
        self.text_mindcode.delete("1.0", tk.END)

        if idx == -1 or n <= 1:
            # Все процессоры вместе или единственный процессор
            self.text_mlog.insert("1.0", self.current_result.mlog)
            self.text_mindcode.insert("1.0", self.current_result.mindcode)

            if n > 1:
                self.lbl_mlog_hint.configure(
                    text=f"Все {n} процессоров вместе  •  {self.current_result.estimated_instructions} строк суммарно  •  {len(self.current_result.rectangles)} прямоугольников"
                )
                self.btn_copy_mlog.configure(text=f"⚡ Скопировать все {n} проц.")
            else:
                self.lbl_mlog_hint.configure(
                    text="Вставьте этот код в процессор через «Вставить из буфера» (Ctrl+V)"
                )
                self.btn_copy_mlog.configure(text="⚡ Скопировать MLOG (для игры)")

            self.btn_next_proc.pack_forget()
        else:
            p = procs[idx]
            self.text_mlog.insert("1.0", p.mlog)
            self.text_mindcode.insert("1.0", p.mindcode)

            self.lbl_mlog_hint.configure(
                text=f"Процессор {p.index} из {n}  •  {p.instruction_count} строк  •  {p.rect_count} прямоугольников"
            )
            self.btn_copy_mlog.configure(text=f"⚡ Скопировать MLOG (Проц #{p.index} из {n})")

            if idx < n - 1:
                self.btn_next_proc.configure(text=f"▶ След. (#{p.index + 1})")
                if not self.btn_next_proc.winfo_manager():
                    self.btn_next_proc.pack(side=tk.LEFT, padx=(6, 0))
            else:
                self.btn_next_proc.pack_forget()

    def _on_next_proc(self):
        """Переход к следующему процессору по цепочке."""
        if not self.current_result or not self.current_result.processors:
            return
        procs = self.current_result.processors
        if self.selected_proc_idx == -1:
            self._select_proc(0)
        elif self.selected_proc_idx < len(procs) - 1:
            self._select_proc(self.selected_proc_idx + 1)

    # ─────────────────────────────────────────────────────────────────────────
    # Переключение вкладок
    # ─────────────────────────────────────────────────────────────────────────

    def _switch_tab(self, tab):
        self.current_tab = tab
        self.frame_preview.pack_forget()
        self.frame_mlog.pack_forget()
        self.frame_mindcode.pack_forget()
        self.frame_schematic.pack_forget()

        for btn in (self.btn_tab_prev, self.btn_tab_mlog, self.btn_tab_mind, self.btn_tab_schem):
            btn.set_color(C_BG_CARD, "#24242c")
            btn.configure(fg=C_TEXT_MUTED)

        if tab == "preview":
            self.frame_preview.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_prev.set_color(C_ACCENT_BLUE, C_ACCENT_BLUE_HVR)
            self.btn_tab_prev.configure(fg="#ffffff")
        elif tab == "mlog":
            self.frame_mlog.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_mlog.set_color(C_ACCENT_GREEN, C_ACCENT_GREEN_HVR)
            self.btn_tab_mlog.configure(fg="#ffffff")
        elif tab == "mindcode":
            self.frame_mindcode.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_mind.set_color(C_ACCENT_BLUE, C_ACCENT_BLUE_HVR)
            self.btn_tab_mind.configure(fg="#ffffff")
        elif tab == "schematic":
            self.frame_schematic.pack(fill=tk.BOTH, expand=True)
            self.btn_tab_schem.set_color(C_ACCENT_ORANGE, C_ACCENT_ORANGE_HVR)
            self.btn_tab_schem.configure(fg="#ffffff")

    # ─────────────────────────────────────────────────────────────────────────
    # Обработчики изменений параметров
    # ─────────────────────────────────────────────────────────────────────────

    def _on_display_changed(self, val):
        self.display_mode = val
        self._run_conversion()

    def _on_proc_changed(self, val):
        self.processor_mode = val
        self._run_conversion()

    def _on_aspect_changed(self, val):
        self.aspect_mode = val
        self._run_conversion()

    def _on_slider_change(self, val):
        self.num_colors = int(float(val))
        self.lbl_colors_val.configure(text=str(self.num_colors))
        self._run_conversion()

    def _on_dither_toggle(self):
        self.dither = self.dither_var.get()
        self._run_conversion()

    def _on_watchdog_toggle(self):
        self._run_conversion()

    def _on_select_file(self):
        filetypes = [
            ("Все поддерживаемые изображения", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif"),
            ("Все файлы", "*.*"),
        ]
        path = filedialog.askopenfilename(title="Выберите изображение", filetypes=filetypes)
        if path:
            self.current_image_path = path
            try:
                with Image.open(path) as img:
                    w, h = img.size
                    name = os.path.basename(path)
                    self.lbl_file_name.configure(
                        text=f"{name} ({w}×{h} px)",
                        fg=C_TEXT_PRIMARY,
                    )
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
                return

            self._run_conversion()

    # ─────────────────────────────────────────────────────────────────────────
    # Выполнение компиляции
    # ─────────────────────────────────────────────────────────────────────────

    def _run_conversion(self):
        if not self.current_image_path:
            return

        target_name = self.entry_target.get().strip() or "display1"

        if self.processor_mode == "multi":
            split_processors = True
            instruction_limit = 1000
        elif self.processor_mode == "world":
            split_processors = False
            instruction_limit = None
        else:  # "single"
            split_processors = False
            instruction_limit = 1000

        watchdog = self.watchdog_var.get()

        try:
            res = ConverterService.convert(
                image_path=self.current_image_path,
                display_key=self.display_mode,
                num_colors=self.num_colors,
                aspect_mode=self.aspect_mode,
                dither=self.dither,
                display_name=target_name,
                instruction_limit=instruction_limit,
                stop_at_end=True,
                split_processors=split_processors,
                watchdog=watchdog,
            )
            self.current_result = res
            self.selected_proc_idx = 0
            self._update_ui_state(res)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка конвертации", str(e))

    def _on_auto_fit(self):
        if not self.current_image_path:
            messagebox.showinfo("Подсказка", "Сначала выберите изображение!")
            return

        target_name = self.entry_target.get().strip() or "display1"
        watchdog = self.watchdog_var.get()

        try:
            res = ConverterService.auto_fit_to_budget(
                image_path=self.current_image_path,
                display_key=self.display_mode,
                max_instructions=950,
                aspect_mode=self.aspect_mode,
                display_name=target_name,
                watchdog=watchdog,
            )
            self.current_result = res
            self.selected_proc_idx = 0
            self.num_colors = res.color_count
            self.slider_colors.set(res.color_count)
            self.lbl_colors_val.configure(text=str(res.color_count))
            self.dither = False
            self.dither_var.set(False)

            self.processor_mode = "single"
            self.seg_proc.select("single")

            self._update_ui_state(res)
            messagebox.showinfo(
                "Авто-подгон завершен",
                f"Параметры оптимизированы под процессор Mindustry!\n\n"
                f"Инструкций mlog: {res.estimated_instructions} (лимит 1000)\n"
                f"Сетка: {res.grid_width}×{res.grid_height} | Цветов: {res.color_count}",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", str(e))

    # ─────────────────────────────────────────────────────────────────────────
    # Обновление состояния UI
    # ─────────────────────────────────────────────────────────────────────────

    def _update_ui_state(self, res: ConversionResult):
        procs = res.processors or []
        n = len(procs)

        # Перестроить панели выбора процессоров
        self._rebuild_proc_tabs(procs)

        # Выбрать процессор и обновить текстовые поля
        if procs:
            if self.selected_proc_idx >= n and self.selected_proc_idx != -1:
                self.selected_proc_idx = 0
            self._select_proc(self.selected_proc_idx)
        else:
            self.text_mlog.delete("1.0", tk.END)
            self.text_mlog.insert("1.0", res.mlog)
            self.text_mindcode.delete("1.0", tk.END)
            self.text_mindcode.insert("1.0", res.mindcode)

        # Бейдж статуса
        inst = res.estimated_instructions
        if n > 1:
            self.badge_status.configure(
                text=f"🔀 {n} процессоров  •  ~{inst} строк всего",
                bg=C_BADGE_MULTI_BG,
                fg=C_BADGE_MULTI_FG,
            )
        elif self.processor_mode == "world":
            self.badge_status.configure(
                text=f"∞ {inst} строк (World Processor)",
                bg=C_BADGE_INFO_BG,
                fg=C_BADGE_INFO_FG,
            )
        elif inst <= 1000:
            self.badge_status.configure(
                text=f"✔ {inst} / 1000 строк (ОК)",
                bg=C_BADGE_OK_BG,
                fg=C_BADGE_OK_FG,
            )
        else:
            self.badge_status.configure(
                text=f"✖ {inst} / 1000 строк (Превышение!)",
                bg=C_BADGE_ERR_BG,
                fg=C_BADGE_ERR_FG,
            )

        # Строка деталей
        extra = ""
        if n > 1:
            extra = f"  •  Процессоров: {n}"
        elif self.processor_mode == "single" and inst > 1000:
            extra = "  •  ⚠️ Выберите режим «Мульти-проц» или «Авто-подгон»"

        self.lbl_details.configure(
            text=(
                f"Прямоугольников: {len(res.rectangles)}"
                f"  •  Цветов: {res.color_count}"
                f"  •  Фон: #{res.bg_color_hex}"
                + extra
            ),
            fg=C_TEXT_MUTED if (n > 1 or inst <= 1000) else C_BADGE_ERR_FG,
        )

        # Обновить вкладку схемы и кнопки схемы
        sr = self._build_schematic_result()
        if sr:
            self.text_schematic.delete("1.0", tk.END)
            self.text_schematic.insert("1.0", sr.schematic_base64)
            self.lbl_schem_info.configure(
                text=f"Блоков: {sr.block_count}  •  Схема: {sr.layout_width}×{sr.layout_height}  •  {sr.processor_count} проц."
            )
            btn_txt = f"📦 Скопировать схему ({sr.processor_count} проц.)" if sr.processor_count > 1 else "📦 Скопировать схему"
            self.btn_copy_schematic.configure(text=btn_txt)
            self.btn_schem_tab_copy.configure(text=btn_txt)

        self._render_canvases(res)

    def _render_canvases(self, res: ConversionResult):
        if not self.current_image_path:
            return

        cw = max(220, self.canvas_disp.winfo_width())
        ch = max(220, self.canvas_disp.winfo_height())
        target_size = min(cw - 20, ch - 20)

        orig = Image.open(self.current_image_path).convert("RGBA")
        orig.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
        self.tk_orig_image = ImageTk.PhotoImage(orig)
        self.canvas_orig.delete("all")
        self.canvas_orig.create_image(cw // 2, ch // 2, image=self.tk_orig_image, anchor=tk.CENTER)

        prev = res.preview_image.copy()
        prev_scaled = prev.resize((target_size, target_size), Image.Resampling.NEAREST)
        self.tk_preview_image = ImageTk.PhotoImage(prev_scaled)
        self.canvas_disp.delete("all")
        self.canvas_disp.create_image(cw // 2, ch // 2, image=self.tk_preview_image, anchor=tk.CENTER)

    # ─────────────────────────────────────────────────────────────────────────
    # Сохранение и буфер обмена
    # ─────────────────────────────────────────────────────────────────────────

    def _get_active_proc(self) -> ProcessorCode | None:
        if not self.current_result:
            return None
        procs = self.current_result.processors
        if procs and 0 <= self.selected_proc_idx < len(procs):
            return procs[self.selected_proc_idx]
        return None

    def _on_copy_mlog(self):
        if not self.current_result:
            messagebox.showinfo("Подсказка", "Сначала выберите изображение!")
            return

        p = self._get_active_proc()
        mlog_text = p.mlog if p else self.current_result.mlog
        n = len(self.current_result.processors or [])

        self.clipboard_clear()
        self.clipboard_append(mlog_text)
        self.update()

        if n > 1:
            if self.selected_proc_idx == -1:
                title = f"Скопированы все {n} процессоров"
                msg = (
                    f"Объединенный MLOG всех {n} процессоров скопирован в буфер!\n\n"
                    "Обратите внимание: для работы в игре разделите код по процессорам."
                )
            else:
                proc_num = p.index if p else 1
                title = f"Процессор #{proc_num} из {n} скопирован"
                msg = (
                    f"MLOG процессора #{proc_num} скопирован в буфер!\n\n"
                    f"1. Вставьте его в процессор #{proc_num} на карте;\n"
                    f"2. Затем нажмите «▶ След. (#{proc_num + 1})» для копирования следующего."
                )
            messagebox.showinfo(title, msg)
        else:
            messagebox.showinfo(
                "Готово к игре!",
                "MLOG скопирован в буфер обмена!\n\n"
                "1. Откройте процессор в Mindustry;\n"
                "2. Нажмите «Изменить»;\n"
                "3. Нажмите «Вставить из буфера» (Ctrl+V).",
            )

    def _on_copy_mindcode(self):
        if not self.current_result:
            messagebox.showinfo("Подсказка", "Сначала выберите изображение!")
            return

        p = self._get_active_proc()
        code = p.mindcode if p else self.current_result.mindcode
        n = len(self.current_result.processors or [])

        self.clipboard_clear()
        self.clipboard_append(code)
        self.update()

        if n > 1 and self.selected_proc_idx != -1:
            proc_num = p.index if p else 1
            messagebox.showinfo("Скопировано", f"Mindcode процессора #{proc_num} скопирован в буфер обмена.")
        else:
            messagebox.showinfo("Скопировано", "Mindcode скопирован в буфер обмена.")

    def _on_save_mlog(self):
        if not self.current_result:
            messagebox.showinfo("Подсказка", "Сначала выберите изображение!")
            return

        procs = self.current_result.processors or []
        base_name = "image_display"
        if self.current_image_path:
            base_name = os.path.splitext(os.path.basename(self.current_image_path))[0]

        if len(procs) <= 1:
            path = filedialog.asksaveasfilename(
                title="Сохранить MLOG",
                initialfile=f"{base_name}.mlog",
                filetypes=[
                    ("Mindustry Logic (*.mlog)", "*.mlog"),
                    ("Текстовый файл", "*.txt"),
                    ("Все файлы", "*.*"),
                ],
            )
            if path:
                mlog_text = procs[0].mlog if procs else self.current_result.mlog
                with open(path, "w", encoding="utf-8") as f:
                    f.write(mlog_text)
                messagebox.showinfo("Готово", f"Файл сохранен:\n{path}")
        else:
            folder = filedialog.askdirectory(title="Выберите папку для сохранения файлов процессоров")
            if folder:
                saved = []
                for p in procs:
                    fname_mlog = f"{base_name}_proc{p.index}.mlog"
                    with open(os.path.join(folder, fname_mlog), "w", encoding="utf-8") as f:
                        f.write(p.mlog)
                    saved.append(fname_mlog)

                    fname_mnd = f"{base_name}_proc{p.index}.mnd"
                    with open(os.path.join(folder, fname_mnd), "w", encoding="utf-8") as f:
                        f.write(p.mindcode)

                fname_comb_mlog = f"{base_name}_combined.mlog"
                with open(os.path.join(folder, fname_comb_mlog), "w", encoding="utf-8") as f:
                    f.write(self.current_result.mlog)
                saved.append(fname_comb_mlog)

                fname_comb_mnd = f"{base_name}_combined.mnd"
                with open(os.path.join(folder, fname_comb_mnd), "w", encoding="utf-8") as f:
                    f.write(self.current_result.mindcode)
                saved.append(fname_comb_mnd)

                messagebox.showinfo(
                    "Готово",
                    f"Сохранено {len(saved)} файлов в папку:\n{folder}\n\n"
                    + "\n".join(f"• {s}" for s in saved)
                    + f"\n\n⚠️ Загружайте файлы proc1, proc2, ... в {len(procs)} процессоров в порядке нумерации!\n"
                    f"Все процессоры должны быть привязаны к дисплею '{self.entry_target.get().strip() or 'display1'}'.",
                )

    # ─────────────────────────────────────────────────────────────────────────
    # Схема (.msch)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_schematic_result(self):
        """Собирает схему из текущего результата. Возвращает SchematicResult или None."""
        if not self.current_result:
            messagebox.showinfo("Подсказка", "Сначала выберите изображение!")
            return None
        try:
            from schematic_builder import PYMSCH_AVAILABLE, build_schematic
            if not PYMSCH_AVAILABLE:
                messagebox.showerror(
                    "Нет pymsch",
                    "Библиотека pymsch не установлена.\n"
                    "Запустите: pip install pymsch\n\n"
                    "После установки перезапустите программу.",
                )
                return None
            name = ""
            if self.current_image_path:
                name = os.path.splitext(os.path.basename(self.current_image_path))[0]
            target = self.entry_target.get().strip() or "display1"
            return build_schematic(
                self.current_result,
                display_key=self.display_mode,
                display_name=target,
                schematic_name=name or "Mindcode Image Display",
            )
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка сборки схемы", str(e))
            return None

    def _on_copy_schematic(self):
        """Копирует схему в буфер обмена для импорта через Mindustry."""
        sr = self._build_schematic_result()
        if sr is None:
            return
        from schematic_builder import copy_schematic_to_clipboard
        if copy_schematic_to_clipboard(sr):
            messagebox.showinfo(
                "📦 Схема скопирована!",
                f"Схема ({sr.block_count} блоков: 1 дисплей + {sr.processor_count} процессоров)\n"
                f"скопирована в буфер обмена!\n\n"
                f"Как импортировать в Mindustry:\n"
                f"1. Откройте Mindustry → Core → Схемы\n"
                f"2. Нажмите «Импорт» → «Вставить из буфера обмена»\n"
                f"3. Схема появится в библиотеке → разместите её на карте\n"
                f"4. Дисплей и {sr.processor_count} процессора уже содержат готовый код!\n\n"
                f"Размер схемы: {sr.layout_width}×{sr.layout_height} тайлов",
            )
        else:
            messagebox.showerror("Ошибка", "Не удалось скопировать схему в буфер обмена.")

    def _on_save_schematic(self):
        """Сохраняет схему в .msch файл."""
        sr = self._build_schematic_result()
        if sr is None:
            return
        base_name = "image_display"
        if self.current_image_path:
            base_name = os.path.splitext(os.path.basename(self.current_image_path))[0]
        path = filedialog.asksaveasfilename(
            title="Сохранить схему Mindustry",
            initialfile=f"{base_name}.msch",
            filetypes=[
                ("Mindustry Schematic (*.msch)", "*.msch"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            from schematic_builder import save_schematic_file
            save_schematic_file(sr, path)
            messagebox.showinfo(
                "Схема сохранена",
                f"Файл сохранен:\n{path}\n\n"
                f"Схема: 1 дисплей + {sr.processor_count} процессоров "
                f"({sr.layout_width}×{sr.layout_height} тайлов)\n\n"
                f"Как импортировать:\n"
                f"Mindustry → Core → Схемы → Импорт → выбрать файл .msch",
            )


def main():
    app = AppGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
