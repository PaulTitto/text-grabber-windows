"""Text Grabber — Clean, Modern Local Offline Windows OCR Desktop App."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from PIL import Image, ImageGrab, ImageTk

from text_grabber_core import (
    CleanupOptions,
    LocalStore,
    PdfDocument,
    clean_text,
    deduplicate_lines,
    find_replace,
    list_ocr_languages,
    ocr_to_table,
    run_ocr,
    sort_lines,
    table_to_csv,
    table_to_tsv,
    transform_case,
)

# Enable Per-Monitor DPI awareness on Windows so screen coordinates match pixels.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(APP_DIR, "app_icon.ico")
INSTALL_PS1 = os.path.join(APP_DIR, "Install_Shortcut.ps1")

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
VK_G = 0x47
VK_F = 0x46
HOTKEY_GRAB_ID = 101
HOTKEY_FRAME_ID = 102

# 60-30-10 Calm Light Theme (WCAG AA compliant)
BG_APP = "#F9FAFB"       # 60% Main background
BG_CARD = "#FFFFFF"      # 30% Card & surface background
BG_SUBTLE = "#F3F4F6"    # Subtle secondary surface
BG_HOVER = "#E5E7EB"     # Hover state
FG_PRIMARY = "#111827"   # Main headings & primary text
FG_SECONDARY = "#4B5563" # Labels & body captions (WCAG AA on #F9FAFB / #FFFFFF)
FG_MUTED = "#6B7280"     # Muted helper text (WCAG AA on #FFFFFF)
ACCENT = "#2563EB"       # 10% Primary CTA & active indicators
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#EFF6FF"
SUCCESS = "#059669"      # Calm emerald (WCAG AA on #ECFDF5 / #F9FAFB)
SUCCESS_SOFT = "#ECFDF5"
BORDER = "#E5E7EB"       # 1px thin card border

UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"


def apply_windows_titlebar(window: tk.Wm) -> None:
    """Enable Windows 11 light titlebar & rounded corners via DWM."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        dark = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        corner = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
    except Exception:
        pass


def get_virtual_screen_bounds() -> tuple[int, int, int, int]:
    """Return (left, top, width, height) of the Windows virtual desktop."""
    user32 = ctypes.windll.user32
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


class RegionOverlay(tk.Toplevel):
    """Fullscreen dimmed overlay for dragging a screenshot capture rectangle."""

    def __init__(
        self,
        master: tk.Tk,
        screenshot: Image.Image,
        bounds: tuple[int, int, int, int],
        mode_label: str,
        on_capture: Any,
        on_cancel: Any,
    ) -> None:
        super().__init__(master)
        self.screenshot = screenshot
        self.on_capture = on_capture
        self.on_cancel = on_cancel

        left, top, width, height = bounds
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{width}x{height}+{left}+{top}")
        self.configure(cursor="crosshair", bg="black")

        self.canvas = tk.Canvas(self, width=width, height=height, highlightthickness=0, bg="black")
        self.canvas.pack(fill="both", expand=True)

        dimmed = Image.blend(screenshot.convert("RGB"), Image.new("RGB", screenshot.size, (15, 23, 42)), alpha=0.45)
        self._bg_photo = ImageTk.PhotoImage(dimmed)
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)

        self.canvas.create_rectangle(24, 24, 396, 60, fill=BG_CARD, outline=BORDER, width=1)
        self.canvas.create_text(
            40,
            42,
            anchor="w",
            text=f"Drag to grab ({mode_label})  •  ESC to cancel",
            fill=FG_PRIMARY,
            font=(UI_FONT, 9, "bold"),
        )

        self._start_x = 0
        self._start_y = 0
        self._rect_id: int | None = None
        self._label_id: int | None = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.focus_force()

    def _on_press(self, event: tk.Event) -> None:
        self._start_x, self._start_y = event.x, event.y
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        if self._label_id:
            self.canvas.delete(self._label_id)
        self._rect_id = self.canvas.create_rectangle(
            self._start_x, self._start_y, event.x, event.y, outline=ACCENT, width=2
        )

    def _on_drag(self, event: tk.Event) -> None:
        if self._rect_id is None:
            return
        x0, y0 = min(self._start_x, event.x), min(self._start_y, event.y)
        x1, y1 = max(self._start_x, event.x), max(self._start_y, event.y)
        self.canvas.coords(self._rect_id, x0, y0, x1, y1)
        if self._label_id:
            self.canvas.delete(self._label_id)
        self._label_id = self.canvas.create_text(
            x0 + 4,
            max(14, y0 - 12),
            anchor="w",
            text=f"{x1 - x0} × {y1 - y0}",
            fill="#FFFFFF",
            font=(UI_FONT, 8, "bold"),
        )

    def _on_release(self, event: tk.Event) -> None:
        x0, y0 = min(self._start_x, event.x), min(self._start_y, event.y)
        x1, y1 = max(self._start_x, event.x), max(self._start_y, event.y)
        self.destroy()
        if x1 - x0 < 5 or y1 - y0 < 5:
            self.on_cancel()
            return
        self.on_capture(self.screenshot.crop((x0, y0, x1, y1)))

    def _cancel(self) -> None:
        self.destroy()
        self.on_cancel()


class GrabFrameWindow(tk.Toplevel):
    """Floating, resizable always-on-top frame for grabbing text from videos or apps."""

    def __init__(self, master: tk.Tk, on_grab_rect: Any) -> None:
        super().__init__(master)
        self.on_grab_rect = on_grab_rect
        self.title("Grab Frame")
        self.geometry("540x230+220+220")
        self.attributes("-topmost", True)
        self.configure(bg="#ff00ff")
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except tk.TclError:
                pass
        apply_windows_titlebar(self)

        try:
            self.attributes("-transparentcolor", "#ff00ff")
        except tk.TclError:
            self.attributes("-alpha", 0.35)

        toolbar = tk.Frame(self, bg=BG_CARD, pady=8, padx=12, highlightbackground=BORDER, highlightthickness=1)
        toolbar.pack(fill="x", side="top")

        tk.Label(
            toolbar,
            text="Arahkan frame ke video atau aplikasi",
            bg=BG_CARD,
            fg=FG_SECONDARY,
            font=(UI_FONT, 9),
        ).pack(side="left")

        tk.Button(
            toolbar,
            text="⌖  Grab",
            command=self._grab,
            bg=ACCENT,
            fg="#FFFFFF",
            activebackground=ACCENT_HOVER,
            activeforeground="#FFFFFF",
            font=(UI_FONT, 9, "bold"),
            relief="flat",
            bd=0,
            padx=14,
            pady=4,
            cursor="hand2",
        ).pack(side="right")

        self.hole = tk.Frame(self, bg="#ff00ff", highlightbackground=ACCENT, highlightthickness=2)
        self.hole.pack(fill="both", expand=True)

    def _grab(self) -> None:
        self.update_idletasks()
        x = self.hole.winfo_rootx()
        y = self.hole.winfo_rooty()
        w = self.hole.winfo_width()
        h = self.hole.winfo_height()
        if w < 10 or h < 10:
            return
        self.withdraw()
        self.after(90, lambda: self._capture_and_restore(x, y, x + w, y + h))

    def _capture_and_restore(self, x0: int, y0: int, x1: int, y1: int) -> None:
        try:
            img = ImageGrab.grab(bbox=(x0, y0, x1, y1), all_screens=True)
        finally:
            if self.winfo_exists():
                self.deiconify()
        self.on_grab_rect(img, "Grab Frame")


class TextGrabberApp(tk.Tk):
    """Clean, modern, local offline Windows OCR & text extraction app."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Text Grabber")
        self.geometry("1160x740")
        self.minsize(900, 600)
        self.configure(bg=BG_APP)
        if os.path.exists(ICON_PATH):
            try:
                self.iconbitmap(ICON_PATH)
            except tk.TclError:
                pass
        apply_windows_titlebar(self)

        self.store = LocalStore()
        self.languages = list_ocr_languages()
        self.current_image: Image.Image | None = None
        self.current_source_name: str = ""
        self.current_ocr_data: dict[str, Any] | None = None
        self.pdf_doc: PdfDocument | None = None
        self.pdf_page_index: int = 0
        self.table_data: list[list[str]] = []

        self._preview_visible = True
        self._cleanup_visible = False
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._preview_scale: float = 1.0
        self._preview_offset: tuple[int, int] = (0, 0)
        self._drag_start: tuple[int, int] | None = None
        self._drag_rect: int | None = None
        self._grab_frame: GrabFrameWindow | None = None
        self._hotkey_stop = threading.Event()
        self._mode_buttons: dict[str, tk.Button] = {}
        self._nav_buttons: dict[str, tk.Button] = {}

        self._configure_styles()
        self._build_ui()
        self._refresh_history_and_snippets()
        self._start_global_hotkey_listener()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "TCombobox",
            fieldbackground=BG_CARD,
            background=BG_CARD,
            foreground=FG_PRIMARY,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            arrowcolor=FG_SECONDARY,
            padding=4,
        )
        style.configure(
            "Treeview",
            background=BG_CARD,
            foreground=FG_PRIMARY,
            fieldbackground=BG_CARD,
            rowheight=30,
            borderwidth=0,
            font=(UI_FONT, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=BG_SUBTLE,
            foreground=FG_SECONDARY,
            borderwidth=0,
            font=(UI_FONT, 9, "bold"),
        )
        style.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", ACCENT)])

    def _build_ui(self) -> None:
        # 1. Above-the-fold Header Card (8px grid: padx=24, pady=16)
        header_wrap = tk.Frame(self, bg=BG_APP, padx=24, pady=16)
        header_wrap.pack(fill="x")

        # Title & Status Row
        title_row = tk.Frame(header_wrap, bg=BG_APP)
        title_row.pack(fill="x", pady=(0, 16))

        title_left = tk.Frame(title_row, bg=BG_APP)
        title_left.pack(side="left")
        tk.Label(
            title_left,
            text="Text Grabber",
            bg=BG_APP,
            fg=FG_PRIMARY,
            font=(UI_FONT, 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_left,
            text="Ekstrak teks dari gambar, video, PDF, dan layar secara lokal",
            bg=BG_APP,
            fg=FG_MUTED,
            font=(UI_FONT, 9),
        ).pack(anchor="w", pady=(2, 0))

        # Status & Summary Chips (Right side of header)
        chips = tk.Frame(title_row, bg=BG_APP)
        chips.pack(side="right")

        self.summary_label = tk.Label(
            chips,
            text=f"◫  {len(self.store.history)} tersimpan",
            bg=BG_CARD,
            fg=FG_SECONDARY,
            font=(UI_FONT, 9),
            padx=12,
            pady=6,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.summary_label.pack(side="left", padx=(0, 8))

        tk.Label(
            chips,
            text="●  Offline OCR",
            bg=SUCCESS_SOFT,
            fg=SUCCESS,
            font=(UI_FONT, 9, "bold"),
            padx=12,
            pady=6,
        ).pack(side="left", padx=(0, 8))

        self._btn(chips, "⌘  Shortcut", self.install_windows_shortcut, outline=True).pack(side="left")

        # 2. Action Toolbar Card (White card with 1px #E5E7EB border, 16px internal padding)
        toolbar_card = tk.Frame(
            header_wrap,
            bg=BG_CARD,
            padx=16,
            pady=12,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        toolbar_card.pack(fill="x")

        # Primary CTA + Secondary Outline Actions (uniform outline icons)
        self._btn(toolbar_card, "⌖  Grab Screen", self.start_fullscreen_grab, accent=True).pack(side="left", padx=(0, 8))
        self._btn(toolbar_card, "⛶  Frame", self.open_grab_frame, outline=True).pack(side="left", padx=(0, 8))
        self._btn(toolbar_card, "◫  Open File", self.open_file_dialog, outline=True).pack(side="left", padx=(0, 8))
        self._btn(toolbar_card, "⎘  Paste", self.paste_clipboard_image, outline=True).pack(side="left")

        # Vertical Divider
        tk.Frame(toolbar_card, width=1, bg=BORDER).pack(side="left", fill="y", padx=16, pady=2)

        # Segmented Mode Switcher
        tk.Label(toolbar_card, text="Mode", bg=BG_CARD, fg=FG_MUTED, font=(UI_FONT, 9, "bold")).pack(side="left", padx=(0, 8))
        self.mode_var = tk.StringVar(value="Standard")
        seg = tk.Frame(toolbar_card, bg=BG_SUBTLE, padx=4, pady=4, highlightbackground=BORDER, highlightthickness=1)
        seg.pack(side="left", padx=(0, 16))
        for label, val in [("Standard", "Standard"), ("1-Line", "Single Line"), ("Table", "Table")]:
            b = tk.Button(
                seg,
                text=label,
                command=lambda v=val: self._set_mode(v),
                relief="flat",
                bd=0,
                padx=10,
                pady=3,
                font=(UI_FONT, 8, "bold"),
                cursor="hand2",
            )
            b.pack(side="left")
            self._mode_buttons[val] = b
        self._set_mode("Standard")

        lang_values = [l["tag"] for l in self.languages] or ["en-US"]
        self.lang_var = tk.StringVar(value=lang_values[0])
        ttk.Combobox(toolbar_card, textvariable=self.lang_var, values=lang_values, state="readonly", width=7).pack(side="left", padx=(0, 12))

        self.auto_copy_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            toolbar_card,
            text="Auto-Copy",
            variable=self.auto_copy_var,
            bg=BG_CARD,
            fg=FG_SECONDARY,
            selectcolor=BG_CARD,
            activebackground=BG_CARD,
            activeforeground=FG_PRIMARY,
            font=(UI_FONT, 9),
        ).pack(side="left")

        self.toggle_preview_btn = self._btn(toolbar_card, "◧  Hide Preview", self._toggle_preview, ghost=True)
        self.toggle_preview_btn.pack(side="right")

        # 3. Main Content Area (24px outer horizontal padding, 16px gap)
        self.paned = tk.PanedWindow(self, orient="horizontal", bg=BG_APP, sashwidth=16, sashrelief="flat")
        self.paned.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # Left Card: Source Preview (16px internal padding)
        self.left_frame = tk.Frame(self.paned, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        self.paned.add(self.left_frame, width=420)

        left_hdr = tk.Frame(self.left_frame, bg=BG_CARD, padx=16, pady=12)
        left_hdr.pack(fill="x")
        self.source_label = tk.Label(left_hdr, text="Preview Sumber", bg=BG_CARD, fg=FG_PRIMARY, font=(UI_FONT, 10, "bold"))
        self.source_label.pack(side="left")
        self._btn(left_hdr, "↻  Re-OCR", self.re_ocr_current, small=True, outline=True).pack(side="right")

        tk.Frame(self.left_frame, height=1, bg=BORDER).pack(fill="x")

        self.preview_canvas = tk.Canvas(self.left_frame, bg=BG_APP, highlightthickness=0, cursor="crosshair")
        self.preview_canvas.pack(fill="both", expand=True, padx=16, pady=16)
        self.preview_canvas.bind("<Configure>", lambda _e: self._render_preview())
        self.preview_canvas.bind("<ButtonPress-1>", self._preview_press)
        self.preview_canvas.bind("<B1-Motion>", self._preview_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._preview_release)

        # PDF Navigation Bar (shown when PDF is loaded)
        self.pdf_bar = tk.Frame(self.left_frame, bg=BG_SUBTLE, padx=16, pady=10)
        self._btn(self.pdf_bar, "◀", lambda: self._pdf_step(-1), small=True, outline=True).pack(side="left")
        self.pdf_page_label = tk.Label(self.pdf_bar, text="1 / 1", bg=BG_SUBTLE, fg=FG_PRIMARY, font=(UI_FONT, 9, "bold"))
        self.pdf_page_label.pack(side="left", padx=12)
        self._btn(self.pdf_bar, "▶", lambda: self._pdf_step(1), small=True, outline=True).pack(side="left")
        self._btn(self.pdf_bar, "OCR All Pages", self.ocr_all_pdf_pages, small=True, accent=True).pack(side="right")

        # Right Card: Clean 3-Item Navigation (Editor | Table | History)
        self.right_frame = tk.Frame(self.paned, bg=BG_CARD, highlightbackground=BORDER, highlightthickness=1)
        self.paned.add(self.right_frame, width=680)

        nav_bar = tk.Frame(self.right_frame, bg=BG_CARD, padx=16, pady=10)
        nav_bar.pack(fill="x")
        for key, label in [("editor", "✎  Editor"), ("table", "⊞  Table"), ("history", "◷  History")]:
            btn = tk.Button(
                nav_bar,
                text=label,
                command=lambda k=key: self._switch_view(k),
                relief="flat",
                bd=0,
                padx=14,
                pady=6,
                font=(UI_FONT, 9, "bold"),
                cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 8))
            self._nav_buttons[key] = btn

        self.counts_label = tk.Label(nav_bar, text="0 chars  •  0 words", bg=BG_CARD, fg=FG_MUTED, font=(UI_FONT, 9))
        self.counts_label.pack(side="right")

        tk.Frame(self.right_frame, height=1, bg=BORDER).pack(fill="x")

        self.view_container = tk.Frame(self.right_frame, bg=BG_CARD)
        self.view_container.pack(fill="both", expand=True)

        self.views: dict[str, tk.Frame] = {}
        self._build_editor_tab()
        self._build_table_tab()
        self._build_history_tab()
        self._switch_view("editor")

        # 4. Minimal Footer
        footer = tk.Frame(self, bg=BG_APP, padx=24, pady=10)
        footer.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Siap  •  Ctrl+Shift+G Grab Screen  •  Ctrl+Shift+F Frame  •  Ctrl+Alt+T Launch")
        tk.Label(footer, textvariable=self.status_var, bg=BG_APP, fg=FG_MUTED, anchor="w", font=(UI_FONT, 8)).pack(side="left")

        self.bind("<Control-v>", lambda _e: self._on_ctrl_v())

    def _switch_view(self, key: str) -> None:
        for k, frame in self.views.items():
            if k == key:
                frame.pack(fill="both", expand=True)
                self._nav_buttons[k].config(bg=ACCENT_SOFT, fg=ACCENT)
            else:
                frame.pack_forget()
                self._nav_buttons[k].config(bg=BG_CARD, fg=FG_SECONDARY)

    def _set_mode(self, mode: str) -> None:
        self.mode_var.set(mode)
        for val, btn in self._mode_buttons.items():
            if val == mode:
                btn.config(bg=BG_CARD, fg=ACCENT)
            else:
                btn.config(bg=BG_SUBTLE, fg=FG_SECONDARY)

    def _build_editor_tab(self) -> None:
        tab = tk.Frame(self.view_container, bg=BG_CARD)
        self.views["editor"] = tab

        bar = tk.Frame(tab, bg=BG_CARD, padx=16, pady=12)
        bar.pack(fill="x")

        self._btn(bar, "⎘  Copy", self.copy_editor_to_clipboard, accent=True, small=True).pack(side="left", padx=(0, 8))
        self._btn(bar, "✦  Cleanup", self._toggle_cleanup_drawer, small=True, outline=True).pack(side="left", padx=(0, 8))
        self._btn(bar, "1-Line", lambda: self._set_editor_text(clean_text(self.get_editor_text(), CleanupOptions(single_line=True))), small=True, ghost=True).pack(side="left", padx=(0, 4))
        self._btn(bar, "Unwrap", lambda: self._set_editor_text(clean_text(self.get_editor_text(), CleanupOptions(unwrap_paragraphs=True))), small=True, ghost=True).pack(side="left")

        self._btn(bar, "✕  Clear", lambda: self._set_editor_text(""), small=True, ghost=True).pack(side="right")
        self._btn(bar, "+ Snippet", self.save_editor_as_snippet, small=True, outline=True).pack(side="right", padx=(0, 8))
        self._btn(bar, "Save .txt", self.save_editor_txt, small=True, outline=True).pack(side="right", padx=(0, 8))

        self.cleanup_drawer = tk.Frame(tab, bg=BG_SUBTLE, padx=16, pady=12, highlightbackground=BORDER, highlightthickness=1)

        row1 = tk.Frame(self.cleanup_drawer, bg=BG_SUBTLE)
        row1.pack(fill="x", pady=(0, 8))
        self.opt_trim = tk.BooleanVar(value=True)
        self.opt_no_blank = tk.BooleanVar(value=False)
        self.opt_unwrap = tk.BooleanVar(value=False)
        self.opt_ascii = tk.BooleanVar(value=False)
        for label, var in [
            ("Trim Spaces", self.opt_trim),
            ("No Blank Lines", self.opt_no_blank),
            ("Unwrap Lines", self.opt_unwrap),
            ("ASCII Only", self.opt_ascii),
        ]:
            tk.Checkbutton(
                row1,
                text=label,
                variable=var,
                bg=BG_SUBTLE,
                fg=FG_PRIMARY,
                selectcolor=BG_CARD,
                activebackground=BG_SUBTLE,
                font=(UI_FONT, 8),
            ).pack(side="left", padx=(0, 10))
        self._btn(row1, "Apply Cleanup", self.apply_cleanup_now, small=True, accent=True).pack(side="right")

        row2 = tk.Frame(self.cleanup_drawer, bg=BG_SUBTLE)
        row2.pack(fill="x", pady=(0, 8))
        for label, fn in [
            ("Deduplicate", lambda: self._set_editor_text(deduplicate_lines(self.get_editor_text()))),
            ("Sort A-Z", lambda: self._set_editor_text(sort_lines(self.get_editor_text()))),
            ("UPPER", lambda: self._set_editor_text(transform_case(self.get_editor_text(), "upper"))),
            ("lower", lambda: self._set_editor_text(transform_case(self.get_editor_text(), "lower"))),
            ("Title Case", lambda: self._set_editor_text(transform_case(self.get_editor_text(), "title"))),
        ]:
            self._btn(row2, label, fn, small=True, outline=True).pack(side="left", padx=(0, 6))

        row3 = tk.Frame(self.cleanup_drawer, bg=BG_SUBTLE)
        row3.pack(fill="x")
        tk.Label(row3, text="Find:", bg=BG_SUBTLE, fg=FG_SECONDARY, font=(UI_FONT, 8, "bold")).pack(side="left")
        self.find_entry = tk.Entry(row3, bg=BG_CARD, fg=FG_PRIMARY, insertbackground=ACCENT, relief="flat", width=18, highlightbackground=BORDER, highlightthickness=1)
        self.find_entry.pack(side="left", padx=8, ipady=3)
        tk.Label(row3, text="Replace:", bg=BG_SUBTLE, fg=FG_SECONDARY, font=(UI_FONT, 8, "bold")).pack(side="left")
        self.replace_entry = tk.Entry(row3, bg=BG_CARD, fg=FG_PRIMARY, insertbackground=ACCENT, relief="flat", width=18, highlightbackground=BORDER, highlightthickness=1)
        self.replace_entry.pack(side="left", padx=8, ipady=3)
        self.regex_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            row3,
            text="Regex",
            variable=self.regex_var,
            bg=BG_SUBTLE,
            fg=FG_SECONDARY,
            selectcolor=BG_CARD,
            activebackground=BG_SUBTLE,
            font=(UI_FONT, 8),
        ).pack(side="left", padx=6)
        self._btn(row3, "Replace All", self._run_find_replace, small=True, outline=True).pack(side="left", padx=6)

        tk.Frame(tab, height=1, bg=BORDER).pack(fill="x")

        self.editor = tk.Text(
            tab,
            bg=BG_CARD,
            fg=FG_PRIMARY,
            insertbackground=ACCENT,
            selectbackground=ACCENT_SOFT,
            selectforeground=FG_PRIMARY,
            font=(MONO_FONT, 11),
            wrap="word",
            relief="flat",
            padx=20,
            pady=16,
            undo=True,
        )
        scroll = tk.Scrollbar(tab, command=self.editor.yview, bg=BG_CARD, troughcolor=BG_APP, relief="flat")
        self.editor.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.editor.pack(fill="both", expand=True)
        self.editor.bind("<KeyRelease>", lambda _e: self._update_counts())

    def _build_table_tab(self) -> None:
        tab = tk.Frame(self.view_container, bg=BG_CARD)
        self.views["table"] = tab

        bar = tk.Frame(tab, bg=BG_CARD, padx=16, pady=12)
        bar.pack(fill="x")
        self._btn(bar, "⎘  Copy TSV", self.copy_table_tsv, small=True, accent=True).pack(side="left", padx=(0, 8))
        self._btn(bar, "Parse OCR", self.parse_last_ocr_as_table, small=True, outline=True).pack(side="left", padx=(0, 8))
        self._btn(bar, "+ Row", self._table_add_row, small=True, ghost=True).pack(side="left", padx=(0, 4))
        self._btn(bar, "+ Col", self._table_add_col, small=True, ghost=True).pack(side="left", padx=(0, 4))
        self._btn(bar, "Del Row", self._table_del_row, small=True, ghost=True).pack(side="left")
        self._btn(bar, "Export CSV", self.export_table_csv, small=True, outline=True).pack(side="right")

        tk.Frame(tab, height=1, bg=BORDER).pack(fill="x")

        tree_wrap = tk.Frame(tab, bg=BG_CARD, padx=16, pady=16)
        tree_wrap.pack(fill="both", expand=True)
        self.table_tree = ttk.Treeview(tree_wrap, show="headings")
        yscroll = tk.Scrollbar(tree_wrap, orient="vertical", command=self.table_tree.yview)
        xscroll = tk.Scrollbar(tree_wrap, orient="horizontal", command=self.table_tree.xview)
        self.table_tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(side="bottom", fill="x")
        self.table_tree.pack(fill="both", expand=True)
        self.table_tree.bind("<Double-1>", self._on_table_double_click)

    def _build_history_tab(self) -> None:
        tab = tk.Frame(self.view_container, bg=BG_CARD)
        self.views["history"] = tab

        h_hdr = tk.Frame(tab, bg=BG_CARD, padx=16, pady=12)
        h_hdr.pack(fill="x")
        tk.Label(h_hdr, text="Recent Grabs", bg=BG_CARD, fg=FG_PRIMARY, font=(UI_FONT, 10, "bold")).pack(side="left")
        self._btn(h_hdr, "Clear", self._clear_history, small=True, ghost=True).pack(side="right")

        self.history_list = tk.Listbox(
            tab,
            bg=BG_APP,
            fg=FG_PRIMARY,
            selectbackground=ACCENT_SOFT,
            selectforeground=ACCENT,
            relief="flat",
            height=10,
            font=(UI_FONT, 9),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.history_list.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.history_list.bind("<<ListboxSelect>>", self._on_history_select)
        self.history_list.bind("<Double-1>", self._on_history_double_click)

        s_hdr = tk.Frame(tab, bg=BG_CARD, padx=16, pady=8)
        s_hdr.pack(fill="x")
        tk.Label(s_hdr, text="Snippets", bg=BG_CARD, fg=FG_PRIMARY, font=(UI_FONT, 10, "bold")).pack(side="left")
        self._btn(s_hdr, "Delete", self._delete_snippet, small=True, ghost=True).pack(side="right")
        self._btn(s_hdr, "+ New", self.save_editor_as_snippet, small=True, outline=True).pack(side="right", padx=(0, 8))

        self.snippet_list = tk.Listbox(
            tab,
            bg=BG_APP,
            fg=FG_PRIMARY,
            selectbackground=ACCENT_SOFT,
            selectforeground=ACCENT,
            relief="flat",
            height=8,
            font=(UI_FONT, 9),
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.snippet_list.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.snippet_list.bind("<<ListboxSelect>>", self._on_snippet_select)
        self.snippet_list.bind("<Double-1>", self._on_snippet_double_click)

    def _btn(
        self,
        parent: tk.Widget,
        text: str,
        command: Any,
        accent: bool = False,
        small: bool = False,
        ghost: bool = False,
        outline: bool = False,
    ) -> tk.Button:
        if accent:
            bg, fg, hover_bg = ACCENT, "#FFFFFF", ACCENT_HOVER
            border_color, border_w = ACCENT, 0
        elif ghost:
            bg, fg, hover_bg = parent.cget("bg"), FG_SECONDARY, BG_SUBTLE
            border_color, border_w = bg, 0
        elif outline:
            bg, fg, hover_bg = BG_CARD, FG_PRIMARY, BG_SUBTLE
            border_color, border_w = BORDER, 1
        else:
            bg, fg, hover_bg = BG_SUBTLE, FG_PRIMARY, BG_HOVER
            border_color, border_w = BORDER, 0

        font = (UI_FONT, 8 if small else 9, "bold" if accent else "normal")
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=FG_PRIMARY if not accent else "#FFFFFF",
            relief="flat",
            bd=0,
            highlightbackground=border_color,
            highlightthickness=border_w,
            padx=12 if small else 14,
            pady=5 if small else 7,
            font=font,
            cursor="hand2",
        )
        btn.bind("<Enter>", lambda _e: btn.config(bg=hover_bg))
        btn.bind("<Leave>", lambda _e: btn.config(bg=bg))
        return btn

    def _toggle_preview(self) -> None:
        if self._preview_visible:
            self.paned.forget(self.left_frame)
            self._preview_visible = False
            self.toggle_preview_btn.config(text="◧  Show Preview")
        else:
            self.paned.add(self.left_frame, before=self.right_frame, width=420)
            self._preview_visible = True
            self.toggle_preview_btn.config(text="◧  Hide Preview")

    def _toggle_cleanup_drawer(self) -> None:
        if self._cleanup_visible:
            self.cleanup_drawer.pack_forget()
            self._cleanup_visible = False
        else:
            self.cleanup_drawer.pack(fill="x", before=self.editor, padx=16, pady=(0, 8))
            self._cleanup_visible = True

    def install_windows_shortcut(self) -> None:
        if not os.path.exists(INSTALL_PS1):
            messagebox.showerror("Installer", f"Missing {INSTALL_PS1}")
            return
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", INSTALL_PS1],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            self.status_var.set("Shortcut Desktop & Start Menu terpasang (Ctrl+Alt+T).")
            messagebox.showinfo(
                "Shortcut Installed",
                "Shortcut Text Grabber terpasang di Desktop & Start Menu!\n\nTekan Ctrl+Alt+T kapan saja di Windows untuk membuka.",
            )
        else:
            messagebox.showerror("Install Error", proc.stderr or "Gagal membuat shortcut.")

    # --- Global Hotkeys (Ctrl+Shift+G, Ctrl+Shift+F) ---
    def _start_global_hotkey_listener(self) -> None:
        def worker() -> None:
            user32 = ctypes.windll.user32
            user32.RegisterHotKey(None, HOTKEY_GRAB_ID, MOD_CONTROL | MOD_SHIFT, VK_G)
            user32.RegisterHotKey(None, HOTKEY_FRAME_ID, MOD_CONTROL | MOD_SHIFT, VK_F)
            msg = wintypes.MSG()
            try:
                while not self._hotkey_stop.is_set():
                    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                        if msg.message == 0x0312:
                            if msg.wParam == HOTKEY_GRAB_ID:
                                self.after(0, self.start_fullscreen_grab)
                            elif msg.wParam == HOTKEY_FRAME_ID:
                                self.after(0, self.open_grab_frame)
                    else:
                        self._hotkey_stop.wait(0.08)
            finally:
                user32.UnregisterHotKey(None, HOTKEY_GRAB_ID)
                user32.UnregisterHotKey(None, HOTKEY_FRAME_ID)

        threading.Thread(target=worker, daemon=True).start()

    # --- Capture Modes ---
    def start_fullscreen_grab(self) -> None:
        self.withdraw()
        self.after(160, self._launch_overlay)

    def _launch_overlay(self) -> None:
        bounds = get_virtual_screen_bounds()
        screenshot = ImageGrab.grab(all_screens=True)

        def on_capture(cropped: Image.Image) -> None:
            self.deiconify()
            self.lift()
            self._close_pdf()
            self._set_preview_image(cropped, "Screen Grab")
            self._run_ocr_async(cropped, "Screen Grab")

        def on_cancel() -> None:
            self.deiconify()
            self.lift()
            self.status_var.set("Grab dibatalkan.")

        RegionOverlay(self, screenshot, bounds, self.mode_var.get(), on_capture, on_cancel)

    def open_grab_frame(self) -> None:
        if self._grab_frame and self._grab_frame.winfo_exists():
            self._grab_frame.lift()
            return

        def on_grab(img: Image.Image, source: str) -> None:
            self._close_pdf()
            self._set_preview_image(img, source)
            self._run_ocr_async(img, source)

        self._grab_frame = GrabFrameWindow(self, on_grab)

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Image or PDF",
            filetypes=[
                ("Supported Files", "*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif *.gif *.pdf"),
                ("Images", "*.png *.jpg *.jpeg *.bmp *.webp *.tiff *.tif *.gif"),
                ("PDF Documents", "*.pdf"),
            ],
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        name = os.path.basename(path)
        if ext == ".pdf":
            self._close_pdf()
            try:
                self.pdf_doc = PdfDocument(path)
                self.pdf_page_index = 0
                self._load_pdf_page()
            except Exception as exc:
                messagebox.showerror("PDF Error", f"Gagal membuka PDF:\n{exc}")
        else:
            self._close_pdf()
            try:
                img = Image.open(path)
                img.load()
                self._set_preview_image(img, name)
                self._run_ocr_async(img, name)
            except Exception as exc:
                messagebox.showerror("Image Error", f"Gagal membuka gambar:\n{exc}")

    def paste_clipboard_image(self) -> None:
        clip = ImageGrab.grabclipboard()
        if isinstance(clip, Image.Image):
            self._close_pdf()
            self._set_preview_image(clip, "Clipboard")
            self._run_ocr_async(clip, "Clipboard")
        elif isinstance(clip, list) and clip and os.path.isfile(clip[0]):
            self._close_pdf()
            img = Image.open(clip[0])
            img.load()
            name = os.path.basename(clip[0])
            self._set_preview_image(img, name)
            self._run_ocr_async(img, name)
        else:
            self.status_var.set("Tidak ada gambar di clipboard.")

    def _on_ctrl_v(self) -> None:
        if self.focus_get() != self.editor:
            self.paste_clipboard_image()

    # --- PDF Handling ---
    def _close_pdf(self) -> None:
        if self.pdf_doc is not None:
            self.pdf_doc.close()
            self.pdf_doc = None
        self.pdf_bar.pack_forget()

    def _load_pdf_page(self) -> None:
        if self.pdf_doc is None:
            return
        img = self.pdf_doc.render_page(self.pdf_page_index, dpi=200)
        name = f"{os.path.basename(self.pdf_doc.path)} (p.{self.pdf_page_index + 1})"
        self.pdf_page_label.config(text=f"{self.pdf_page_index + 1} / {self.pdf_doc.page_count}")
        self.pdf_bar.pack(fill="x", side="bottom")
        self._set_preview_image(img, name)
        self._run_ocr_async(img, name)

    def _pdf_step(self, delta: int) -> None:
        if self.pdf_doc is None:
            return
        nxt = self.pdf_page_index + delta
        if 0 <= nxt < self.pdf_doc.page_count:
            self.pdf_page_index = nxt
            self._load_pdf_page()

    def ocr_all_pdf_pages(self) -> None:
        if self.pdf_doc is None:
            return
        doc = self.pdf_doc
        lang_tag = self.lang_var.get() or None
        self.status_var.set(f"Memproses {doc.page_count} halaman PDF secara lokal...")

        def worker() -> None:
            chunks: list[str] = []
            try:
                for i in range(doc.page_count):
                    self.after(0, lambda idx=i: self.status_var.set(f"OCR halaman {idx + 1} / {doc.page_count}..."))
                    page_img = doc.render_page(i, dpi=200)
                    res = run_ocr(page_img, lang_tag)
                    cleaned = clean_text(res.get("text", ""), self._current_cleanup_options())
                    chunks.append(f"--- Page {i + 1} ---\n{cleaned}")
                combined = "\n\n".join(chunks)
                self.after(0, lambda: self._apply_text_result(combined, os.path.basename(doc.path), "PDF All"))
            except Exception as exc:
                self.after(0, lambda: self.status_var.set(f"PDF OCR gagal: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    # --- Preview & Sub-region Selection ---
    def _set_preview_image(self, img: Image.Image, source_name: str) -> None:
        self.current_image = img
        self.current_source_name = source_name
        self.source_label.config(text=f"{source_name}  •  {img.width}×{img.height}")
        self._render_preview()

    def _render_preview(self) -> None:
        self.preview_canvas.delete("all")
        if self.current_image is None:
            self.preview_canvas.create_text(
                max(100, self.preview_canvas.winfo_width() // 2),
                max(100, self.preview_canvas.winfo_height() // 2),
                text="Klik Grab Screen, Open File,\natau Paste gambar dari clipboard",
                fill=FG_MUTED,
                font=(UI_FONT, 10),
                justify="center",
            )
            return

        cw = max(1, self.preview_canvas.winfo_width())
        ch = max(1, self.preview_canvas.winfo_height())
        iw, ih = self.current_image.size
        scale = min((cw - 16) / iw, (ch - 16) / ih, 1.0)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        ox, oy = (cw - nw) // 2, (ch - nh) // 2

        self._preview_scale = scale
        self._preview_offset = (ox, oy)
        resized = self.current_image.resize((nw, nh), Image.Resampling.LANCZOS)
        self._preview_photo = ImageTk.PhotoImage(resized)
        self.preview_canvas.create_image(ox, oy, anchor="nw", image=self._preview_photo)

    def _preview_press(self, event: tk.Event) -> None:
        if self.current_image is None:
            return
        self._drag_start = (event.x, event.y)
        if self._drag_rect:
            self.preview_canvas.delete(self._drag_rect)
        self._drag_rect = self.preview_canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=ACCENT, width=2
        )

    def _preview_drag(self, event: tk.Event) -> None:
        if self._drag_start and self._drag_rect:
            self.preview_canvas.coords(self._drag_rect, self._drag_start[0], self._drag_start[1], event.x, event.y)

    def _preview_release(self, event: tk.Event) -> None:
        if self.current_image is None or not self._drag_start:
            return
        x0, y0 = min(self._drag_start[0], event.x), min(self._drag_start[1], event.y)
        x1, y1 = max(self._drag_start[0], event.x), max(self._drag_start[1], event.y)
        self._drag_start = None
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        ox, oy = self._preview_offset
        scale = self._preview_scale
        ix0 = max(0, int((x0 - ox) / scale))
        iy0 = max(0, int((y0 - oy) / scale))
        ix1 = min(self.current_image.width, int((x1 - ox) / scale))
        iy1 = min(self.current_image.height, int((y1 - oy) / scale))
        if ix1 - ix0 > 5 and iy1 - iy0 > 5:
            self._run_ocr_async(self.current_image.crop((ix0, iy0, ix1, iy1)), f"{self.current_source_name} [Region]")

    # --- OCR Execution ---
    def _current_cleanup_options(self) -> CleanupOptions:
        return CleanupOptions(
            trim_lines=self.opt_trim.get(),
            remove_blank_lines=self.opt_no_blank.get(),
            unwrap_paragraphs=self.opt_unwrap.get(),
            single_line=(self.mode_var.get() == "Single Line"),
            remove_non_ascii=self.opt_ascii.get(),
        )

    def re_ocr_current(self) -> None:
        if self.current_image is not None:
            self._run_ocr_async(self.current_image, self.current_source_name)

    def _run_ocr_async(self, img: Image.Image, source: str) -> None:
        mode = self.mode_var.get()
        lang_tag = self.lang_var.get() or None
        self.status_var.set(f"Menjalankan OCR lokal ({mode})...")

        def worker() -> None:
            try:
                data = run_ocr(img, lang_tag)
                self.after(0, lambda: self._on_ocr_complete(data, source, mode))
            except Exception as exc:
                self.after(0, lambda: self.status_var.set(f"OCR error: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ocr_complete(self, data: dict[str, Any], source: str, mode: str) -> None:
        self.current_ocr_data = data
        if mode == "Table":
            table = ocr_to_table(data)
            self._load_table(table)
            self._apply_text_result(table_to_tsv(table), source, mode, switch_to_table=True)
        else:
            cleaned = clean_text(data.get("text", ""), self._current_cleanup_options())
            self._apply_text_result(cleaned, source, mode, switch_to_table=False)

    def _apply_text_result(self, text: str, source: str, mode: str, switch_to_table: bool = False) -> None:
        self._set_editor_text(text)
        self.store.add_history(text, source, mode)
        self._refresh_history_and_snippets()
        if self.auto_copy_var.get() and text.strip():
            self._copy_text(text)
            self.status_var.set(f"Teks diambil ({source}) dan disalin ke clipboard.")
        else:
            self.status_var.set(f"Teks diambil ({source}).")
        self._switch_view("table" if switch_to_table else "editor")

    # --- Editor & Cleanup ---
    def get_editor_text(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def _set_editor_text(self, text: str) -> None:
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self._update_counts()

    def _update_counts(self) -> None:
        txt = self.get_editor_text()
        chars = len(txt)
        words = len(txt.split()) if txt.strip() else 0
        self.counts_label.config(text=f"{chars} chars  •  {words} words")

    def apply_cleanup_now(self) -> None:
        self._set_editor_text(clean_text(self.get_editor_text(), self._current_cleanup_options()))
        self.status_var.set("Cleanup diterapkan.")

    def _run_find_replace(self) -> None:
        try:
            new_text, count = find_replace(
                self.get_editor_text(),
                self.find_entry.get(),
                self.replace_entry.get(),
                use_regex=self.regex_var.get(),
            )
            self._set_editor_text(new_text)
            self.status_var.set(f"Mengganti {count} kecocokan.")
        except Exception as exc:
            messagebox.showerror("Find & Replace", str(exc))

    def _copy_text(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()

    def copy_editor_to_clipboard(self) -> None:
        txt = self.get_editor_text()
        if txt:
            self._copy_text(txt)
            self.status_var.set("Disalin ke clipboard.")

    def save_editor_txt(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text Files", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.get_editor_text())
        self.status_var.set(f"Disimpan: {os.path.basename(path)}.")

    def save_editor_as_snippet(self) -> None:
        txt = self.get_editor_text().strip()
        if not txt:
            messagebox.showinfo("Save Snippet", "Editor masih kosong.")
            return
        title = simpledialog.askstring("Save Snippet", "Judul snippet:", parent=self)
        if title is not None:
            self.store.add_snippet(title, txt)
            self._refresh_history_and_snippets()
            self.status_var.set("Snippet tersimpan.")

    # --- Spreadsheet / Table Editor ---
    def parse_last_ocr_as_table(self) -> None:
        if not self.current_ocr_data:
            self.status_var.set("Ambil gambar atau PDF terlebih dahulu.")
            return
        self._load_table(ocr_to_table(self.current_ocr_data))
        self._switch_view("table")
        self.status_var.set("OCR dikonversi menjadi tabel.")

    def _load_table(self, rows: list[list[str]]) -> None:
        self.table_data = [list(r) for r in rows] if rows else [[""]]
        num_cols = max((len(r) for r in self.table_data), default=1)
        for r in self.table_data:
            while len(r) < num_cols:
                r.append("")

        cols = [f"C{i + 1}" for i in range(num_cols)]
        self.table_tree.delete(*self.table_tree.get_children())
        self.table_tree["columns"] = cols
        for idx, c in enumerate(cols):
            self.table_tree.heading(c, text=f"Col {idx + 1}")
            self.table_tree.column(c, width=130, anchor="w")
        for r in self.table_data:
            self.table_tree.insert("", "end", values=r)

    def _on_table_double_click(self, event: tk.Event) -> None:
        row_id = self.table_tree.identify_row(event.y)
        col_id = self.table_tree.identify_column(event.x)
        if not row_id or not col_id:
            return
        col_idx = int(col_id.replace("#", "")) - 1
        row_idx = self.table_tree.index(row_id)
        bbox = self.table_tree.bbox(row_id, col_id)
        if not bbox:
            return
        x, y, w, h = bbox
        entry = tk.Entry(self.table_tree, bg=BG_CARD, fg=FG_PRIMARY, insertbackground=ACCENT, relief="flat", highlightbackground=ACCENT, highlightthickness=1)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, self.table_data[row_idx][col_idx])
        entry.select_range(0, "end")
        entry.focus_set()

        def commit(_e: Any = None) -> None:
            self.table_data[row_idx][col_idx] = entry.get()
            self.table_tree.item(row_id, values=self.table_data[row_idx])
            entry.destroy()

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)
        entry.bind("<Escape>", lambda _e: entry.destroy())

    def _table_add_row(self) -> None:
        cols = max(1, len(self.table_tree["columns"]))
        if not self.table_data:
            self._load_table([[""] * cols])
            return
        new_row = [""] * cols
        self.table_data.append(new_row)
        self.table_tree.insert("", "end", values=new_row)

    def _table_add_col(self) -> None:
        for r in self.table_data:
            r.append("")
        self._load_table(self.table_data)

    def _table_del_row(self) -> None:
        sel = self.table_tree.selection()
        if not sel:
            return
        idx = self.table_tree.index(sel[0])
        self.table_tree.delete(sel[0])
        if 0 <= idx < len(self.table_data):
            self.table_data.pop(idx)

    def copy_table_tsv(self) -> None:
        if self.table_data:
            self._copy_text(table_to_tsv(self.table_data))
            self.status_var.set("Tabel disalin sebagai TSV.")

    def export_table_csv(self) -> None:
        if not self.table_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not path:
            return
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(table_to_csv(self.table_data))
        self.status_var.set(f"Diekspor ke {os.path.basename(path)}.")

    # --- History & Snippets ---
    def _refresh_history_and_snippets(self) -> None:
        self.summary_label.config(text=f"◫  {len(self.store.history)} tersimpan")
        self.history_list.delete(0, "end")
        for item in self.store.history:
            preview = item["text"].replace("\n", " ")[:75]
            self.history_list.insert("end", f"[{item['timestamp']}] {preview}")

        self.snippet_list.delete(0, "end")
        for snip in self.store.snippets:
            preview = snip["text"].replace("\n", " ")[:75]
            self.snippet_list.insert("end", f"{snip['title']} — {preview}")

    def _on_history_select(self, _e: Any) -> None:
        sel = self.history_list.curselection()
        if sel:
            self._set_editor_text(self.store.history[sel[0]]["text"])

    def _on_history_double_click(self, _e: Any) -> None:
        sel = self.history_list.curselection()
        if sel:
            self._copy_text(self.store.history[sel[0]]["text"])
            self.status_var.set("Item history disalin.")

    def _clear_history(self) -> None:
        self.store.clear_history()
        self._refresh_history_and_snippets()

    def _on_snippet_select(self, _e: Any) -> None:
        sel = self.snippet_list.curselection()
        if sel:
            self._set_editor_text(self.store.snippets[sel[0]]["text"])

    def _on_snippet_double_click(self, _e: Any) -> None:
        sel = self.snippet_list.curselection()
        if sel:
            self._copy_text(self.store.snippets[sel[0]]["text"])
            self.status_var.set("Snippet disalin.")

    def _delete_snippet(self) -> None:
        sel = self.snippet_list.curselection()
        if sel:
            self.store.delete_snippet(sel[0])
            self._refresh_history_and_snippets()

    def _on_close(self) -> None:
        self._hotkey_stop.set()
        self._close_pdf()
        self.destroy()


def main() -> None:
    app = TextGrabberApp()
    app.mainloop()


if __name__ == "__main__":
    main()
