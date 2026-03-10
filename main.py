from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageEnhance, ImageFont
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

# ── Opsiyonel: HEIC desteği ────────────────────────────────────────────────
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False

# ── Opsiyonel: sistem tepsisi ──────────────────────────────────────────────
try:
    import pystray
    TRAY_SUPPORT = True
except ImportError:
    TRAY_SUPPORT = False

# ── AVIF desteği kontrolü ──────────────────────────────────────────────────
def _check_avif() -> bool:
    try:
        Image.new("RGB", (1, 1)).save(io.BytesIO(), "AVIF")
        return True
    except (KeyError, OSError, ValueError):
        return False

AVIF_SUPPORT = _check_avif()

# ── Kalıcı ayarlar (palette'den önce tanımlanmalı) ────────────────────────
SETTINGS_PATH = Path.home() / ".gorsel_donusturucu.json"
HISTORY_PATH  = Path.home() / ".gorsel_donusturucu_history.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "out_dir": str(Path.home() / "Dönüştürülen"),
    "format": "JPG", "quality": 85, "png_compress": 6,
    "resize": False, "width": "1920", "height": "1080", "keep_ratio": True,
    "prefix": "", "suffix": "", "keepname": True,
    "numbering": False, "nstart": "1", "npad": "3",
    "recursive": True, "rm_exif": False, "overwrite": False,
    "subfolder": False, "workers": 4,
    "theme": "dark",
    "window_x": -1, "window_y": -1, "window_w": 1240, "window_h": 860,
    "brightness": 100, "contrast": 100, "saturation": 100,
    "rotation": "Yok",
    "wm_enabled": False, "wm_text": "", "wm_opacity": 160,
    "wm_position": "Sağ Alt", "wm_size": 36,
    "max_size_enabled": False, "max_size_kb": 500,
    "minimize_to_tray": False,
}

def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except Exception:
        return DEFAULT_SETTINGS.copy()

def save_settings(data: dict) -> None:
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def append_history(entry: dict) -> None:
    try:
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
        history.insert(0, entry)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history[:100], f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def load_history() -> list:
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

# ── Renk paletleri ─────────────────────────────────────────────────────────
_PALETTES = {
    "dark": {
        "BG":         "#0d1117",
        "SURFACE":    "#13171f",
        "CARD":       "#1c2132",
        "ACCENT":     "#7c3aed",
        "ACCENT_H":   "#6d28d9",
        "TEXT":       "#e2e8f0",
        "TEXT_DIM":   "#94a3b8",
        "TEXT_MUTED": "#64748b",
        "DANGER":     "#dc2626",
        "BORDER":     "#2d3550",
        "BTN_SECONDARY_BG":    "#1c2132",
        "BTN_SECONDARY_HO":    "#252e48",
        "BTN_DANGER_BG":       "#1f1520",
        "BTN_DANGER_HO":       "#2d1b2e",
        "BTN_DANGER_BORDER":   "#5b2333",
        "SLIDER_BG":           "#2d3550",
        "SIG_COLOR":           "#3d2f6b",
    },
    "light": {
        "BG":         "#f0f4f8",
        "SURFACE":    "#ffffff",
        "CARD":       "#e8edf3",
        "ACCENT":     "#7c3aed",
        "ACCENT_H":   "#6d28d9",
        "TEXT":       "#1e293b",
        "TEXT_DIM":   "#475569",
        "TEXT_MUTED": "#94a3b8",
        "DANGER":     "#dc2626",
        "BORDER":     "#cbd5e1",
        "BTN_SECONDARY_BG":    "#e8edf3",
        "BTN_SECONDARY_HO":    "#dde3ed",
        "BTN_DANGER_BG":       "#fef2f2",
        "BTN_DANGER_HO":       "#fee2e2",
        "BTN_DANGER_BORDER":   "#fca5a5",
        "SLIDER_BG":           "#cbd5e1",
        "SIG_COLOR":           "#a78bfa",
    },
}

def _load_palette(theme: str) -> dict:
    key = "light" if theme == "light" else "dark"
    return _PALETTES[key]

# Başlangıçta ayarlardan temayı oku
_startup_theme = load_settings().get("theme", "dark")
_P = _load_palette(_startup_theme)

BG         = _P["BG"]
SURFACE    = _P["SURFACE"]
CARD       = _P["CARD"]
ACCENT     = _P["ACCENT"]
ACCENT_H   = _P["ACCENT_H"]
TEXT       = _P["TEXT"]
TEXT_DIM   = _P["TEXT_DIM"]
TEXT_MUTED = _P["TEXT_MUTED"]
DANGER     = _P["DANGER"]
BORDER     = _P["BORDER"]

# ── Format tabloları ───────────────────────────────────────────────────────
SUPPORTED_INPUT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif", ".avif"}
if HEIC_SUPPORT:
    SUPPORTED_INPUT |= {".heic", ".heif"}

OUTPUT_FORMATS = ["JPG", "PNG", "WEBP", "BMP", "TIFF"]
if AVIF_SUPPORT:
    OUTPUT_FORMATS.append("AVIF")

EXT_MAP = {"JPG": ".jpg", "PNG": ".png", "WEBP": ".webp", "BMP": ".bmp", "TIFF": ".tiff", "AVIF": ".avif"}
PIL_MAP = {"JPG": "JPEG", "PNG": "PNG",  "WEBP": "WEBP",  "BMP": "BMP",  "TIFF": "TIFF",  "AVIF": "AVIF"}

ROTATION_OPTIONS = ["Yok", "90° Saat Yönü", "90° Ters Yön", "180°", "Yatay Ayna", "Dikey Ayna"]
WM_POSITIONS     = ["Sağ Alt", "Sol Alt", "Sağ Üst", "Sol Üst", "Merkez"]

_THEME_LABELS  = ["🌙 Koyu", "☀️ Açık", "🖥 Sistem"]
_THEME_VALUES  = {"🌙 Koyu": "dark", "☀️ Açık": "light", "🖥 Sistem": "system"}
_THEME_RLABELS = {"dark": "🌙 Koyu", "light": "☀️ Açık", "system": "🖥 Sistem"}


@dataclass
class ConversionSettings:
    """Bir dönüştürme işleminin tüm parametrelerini taşır."""

    fmt: str
    pil_fmt: str
    out_ext: str
    quality: int
    png_compress: int
    do_resize: bool
    tw: int | None
    th: int | None
    keep_ratio: bool
    rm_exif: bool
    overwrite: bool
    subfolder: bool
    prefix: str
    suffix: str
    keepname: bool
    do_num: bool
    nstart: int
    npad: int
    rotation: str
    brightness: int
    contrast: int
    saturation: int
    wm_enabled: bool
    wm_text: str
    wm_opacity: int
    wm_position: str
    wm_size: int
    max_size_bytes: int
    workers: int
    files: list[str] = field(default_factory=list)


@dataclass
class HistoryEntry:
    """Tek bir dönüştürme oturumunun özeti."""

    date: str
    fmt: str
    ok: int
    skip: int
    err: int
    out_dir: str
    total_in: int
    total_out: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date, "format": self.fmt,
            "ok": self.ok, "skip": self.skip, "err": self.err,
            "out_dir": self.out_dir, "total_in": self.total_in, "total_out": self.total_out,
        }

# ── Görüntü işleme pipeline ────────────────────────────────────────────────
def apply_pipeline(img: Image.Image, *,
                   do_resize: bool, tw: int | None, th: int | None, keep_ratio: bool,
                   rotation: str,
                   brightness: int, contrast: int, saturation: int,
                   wm_enabled: bool, wm_text: str, wm_opacity: int,
                   wm_position: str, wm_size: int) -> Image.Image:

    # 1. Boyutlandırma
    if do_resize and tw:
        if keep_ratio:
            ratio = img.height / img.width
            img = img.resize((tw, max(1, int(tw * ratio))), Image.LANCZOS)
        else:
            img = img.resize((tw, th), Image.LANCZOS)

    # 2. Döndürme / Ayna
    if rotation == "90° Saat Yönü":
        img = img.rotate(-90, expand=True)
    elif rotation == "90° Ters Yön":
        img = img.rotate(90, expand=True)
    elif rotation == "180°":
        img = img.rotate(180)
    elif rotation == "Yatay Ayna":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif rotation == "Dikey Ayna":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)

    # 3. Parlaklık / Kontrast / Doygunluk
    if brightness != 100:
        img = ImageEnhance.Brightness(img).enhance(brightness / 100)
    if contrast != 100:
        img = ImageEnhance.Contrast(img).enhance(contrast / 100)
    if saturation != 100:
        img = ImageEnhance.Color(img).enhance(saturation / 100)

    # 4. Filigran
    if wm_enabled and wm_text:
        base = img.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", wm_size)
        except (OSError, IOError):
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), wm_text, font=font)
        tw2, th2 = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 16
        w, h = base.size
        pos_map = {
            "Sağ Alt":  (w - tw2 - pad, h - th2 - pad),
            "Sol Alt":  (pad, h - th2 - pad),
            "Sağ Üst":  (w - tw2 - pad, pad),
            "Sol Üst":  (pad, pad),
            "Merkez":   ((w - tw2) // 2, (h - th2) // 2),
        }
        x, y = pos_map.get(wm_position, (pad, pad))
        draw.text((x + 1, y + 1), wm_text, font=font, fill=(0, 0, 0, wm_opacity))
        draw.text((x, y), wm_text, font=font, fill=(255, 255, 255, wm_opacity))
        img = Image.alpha_composite(base, overlay)

    return img


def convert_mode(img: Image.Image, pil_fmt: str) -> Image.Image:
    """Hedef formata uygun renk moduna dönüştür."""
    if pil_fmt in ("JPEG", "WEBP", "AVIF", "BMP", "TIFF"):
        if img.mode not in ("RGB", "L"):
            if img.mode in ("RGBA", "LA", "PA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            else:
                img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")
    return img


class ImageConverter(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self._settings = load_settings()
        self._apply_theme(self._settings["theme"])
        self.configure(fg_color=BG)
        self.title("Görsel Dönüştürücü")
        s = self._settings
        geo = f"{s['window_w']}x{s['window_h']}"
        if s["window_x"] >= 0 and s["window_y"] >= 0:
            geo += f"+{s['window_x']}+{s['window_y']}"
        self.geometry(geo)
        self.minsize(960, 700)
        self.files: list[str] = []
        self.cancel_flag = False
        self._ratio: float = 1080.0 / 1920.0
        self._ratio_lock: bool = False
        self._preview_ref = None
        self._tray_icon = None
        self._build_ui()
        self._load_settings_to_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Tema ────────────────────────────────────────────────────────────────
    @staticmethod
    def _apply_theme(theme: str):
        ctk.set_appearance_mode("light" if theme == "light" else "dark")
        ctk.set_default_color_theme("blue")

    # ── Pencere kapat ────────────────────────────────────────────────────────
    def _on_close(self):
        self._save_settings_from_ui()
        if TRAY_SUPPORT and self.minimize_tray_var.get():
            self._start_tray()
        else:
            self.destroy()

    def _start_tray(self):
        self.withdraw()
        icon_img = Image.new("RGBA", (64, 64), (124, 58, 237, 255))
        menu = pystray.Menu(
            pystray.MenuItem("Aç", self._restore_from_tray),
            pystray.MenuItem("Çıkış", self._quit_from_tray),
        )
        self._tray_icon = pystray.Icon("GorselDonusturucu", icon_img, "Görsel Dönüştürücü", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _restore_from_tray(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
            self._tray_icon = None
        self.after(0, self.deiconify)

    def _quit_from_tray(self, icon=None, item=None):
        if self._tray_icon:
            self._tray_icon.stop()
        self._save_settings_from_ui()
        self.after(0, self.destroy)

    # ── Ayar kaydet / yükle ─────────────────────────────────────────────────
    def _save_settings_from_ui(self):
        save_settings({
            "out_dir": self.out_var.get(), "format": self.fmt_var.get(),
            "quality": self.q_var.get(), "png_compress": self.png_compress_var.get(),
            "resize": self.resize_var.get(), "width": self.w_var.get(),
            "height": self.h_var.get(), "keep_ratio": self.ratio_var.get(),
            "prefix": self.pfx_var.get(), "suffix": self.sfx_var.get(),
            "keepname": self.keepname_var.get(), "numbering": self.num_var.get(),
            "nstart": self.nstart_var.get(), "npad": self.npad_var.get(),
            "recursive": self.recursive_var.get(), "rm_exif": self.exif_var.get(),
            "overwrite": self.overwrite_var.get(), "subfolder": self.subfolder_var.get(),
            "workers": self.workers_var.get(), "theme": self.theme_var.get(),
            "window_x": self.winfo_x(), "window_y": self.winfo_y(),
            "window_w": self.winfo_width(), "window_h": self.winfo_height(),
            "brightness": self.brightness_var.get(), "contrast": self.contrast_var.get(),
            "saturation": self.saturation_var.get(), "rotation": self.rotation_var.get(),
            "wm_enabled": self.wm_enabled_var.get(), "wm_text": self.wm_text_var.get(),
            "wm_opacity": self.wm_opacity_var.get(), "wm_position": self.wm_position_var.get(),
            "wm_size": self.wm_size_var.get(),
            "max_size_enabled": self.max_size_var.get(), "max_size_kb": self.max_size_kb_var.get(),
            "minimize_to_tray": self.minimize_tray_var.get() if TRAY_SUPPORT else False,
        })

    def _load_settings_to_ui(self):
        s = self._settings
        self.out_var.set(s["out_dir"])
        self.fmt_var.set(s["format"] if s["format"] in OUTPUT_FORMATS else "JPG")
        self.q_var.set(s["quality"])
        self.q_lbl.configure(text=f"{s['quality']}%")
        self.png_compress_var.set(s["png_compress"])
        self.png_compress_lbl.configure(text=str(s["png_compress"]))
        self.resize_var.set(s["resize"])
        self.w_var.set(s["width"]); self.h_var.set(s["height"])
        self.ratio_var.set(s["keep_ratio"])
        self.pfx_var.set(s["prefix"]); self.sfx_var.set(s["suffix"])
        self.keepname_var.set(s["keepname"]); self.num_var.set(s["numbering"])
        self.nstart_var.set(s["nstart"]); self.npad_var.set(s["npad"])
        self.recursive_var.set(s["recursive"]); self.exif_var.set(s["rm_exif"])
        self.overwrite_var.set(s["overwrite"]); self.subfolder_var.set(s["subfolder"])
        self.workers_var.set(s.get("workers", 4))
        self.theme_var.set(s["theme"])
        self.theme_seg.set(_THEME_RLABELS.get(s["theme"], "🌙 Koyu"))
        self.brightness_var.set(s["brightness"])
        self.brightness_lbl.configure(text=f"{s['brightness']}%")
        self.contrast_var.set(s["contrast"])
        self.contrast_lbl.configure(text=f"{s['contrast']}%")
        self.saturation_var.set(s["saturation"])
        self.saturation_lbl.configure(text=f"{s['saturation']}%")
        self.rotation_var.set(s["rotation"])
        self.wm_enabled_var.set(s["wm_enabled"]); self.wm_text_var.set(s["wm_text"])
        self.wm_opacity_var.set(s["wm_opacity"])
        self.wm_opacity_lbl.configure(text=str(s["wm_opacity"]))
        self.wm_position_var.set(s["wm_position"]); self.wm_size_var.set(s["wm_size"])
        self.wm_size_lbl.configure(text=str(s["wm_size"]))
        self.max_size_var.set(s["max_size_enabled"]); self.max_size_kb_var.set(str(s["max_size_kb"]))
        if TRAY_SUPPORT:
            self.minimize_tray_var.set(s["minimize_to_tray"])
        self._on_format(); self._on_resize(); self._on_num(); self._on_wm_toggle()

    # ─────────────────────────── UI ────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()
        self.drop_target_register(DND_FILES)
        self.dnd_bind("<<Drop>>", self._on_drop)

    # ── Sol Panel ──────────────────────────────────────────────────────────
    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        left.grid(row=0, column=0, padx=(14, 6), pady=14, sticky="nsew")
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        if not HEIC_SUPPORT:
            ctk.CTkLabel(left, text="⚠ HEIC desteği için: pip install pillow-heif",
                         font=ctk.CTkFont("Segoe UI", 9), text_color="#f59e0b",
                         ).grid(row=0, column=0, sticky="w", padx=12, pady=(6, 0))

        # Toolbar
        tb = ctk.CTkFrame(left, fg_color="transparent")
        tb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 4))
        _btn = dict(height=34, corner_radius=8, font=ctk.CTkFont("Segoe UI", 12))

        ctk.CTkButton(tb, text="📂  Klasör", width=110, fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.add_folder, **_btn).pack(side="left", padx=(0, 4))
        ctk.CTkButton(tb, text="🖼  Dosya", width=100, fg_color=CARD, hover_color="#252e48",
                      border_width=1, border_color=BORDER,
                      command=self.add_files, **_btn).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="🗑  Temizle", width=95, fg_color="#1f1520", hover_color="#2d1b2e",
                      border_width=1, border_color="#5b2333", text_color=DANGER,
                      command=self.clear_files, **_btn).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="🕘", width=40, fg_color=CARD, hover_color="#252e48",
                      border_width=1, border_color=BORDER,
                      command=self._show_history, **_btn).pack(side="left", padx=4)

        self.count_lbl = ctk.CTkLabel(tb, text="0 dosya",
                                      font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED)
        self.count_lbl.pack(side="right", padx=8)

        # Dosya listesi
        lf = ctk.CTkFrame(left, fg_color=CARD, corner_radius=10)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=2)
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            lf, bg=CARD, fg=TEXT, selectbackground=ACCENT, selectforeground="#fff",
            font=("Consolas", 10), borderwidth=0, highlightthickness=0, activestyle="none",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.listbox.bind("<Delete>",          self._delete_selected)
        self.listbox.bind("<Button-3>",        self._right_click)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", self._open_in_explorer)
        self.listbox.bind("<Control-a>",       lambda _: self.listbox.select_set(0, tk.END))
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind("<<Drop>>", self._on_drop)

        sb = ctk.CTkScrollbar(lf, command=self.listbox.yview,
                              button_color=ACCENT, button_hover_color=ACCENT_H)
        sb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 4))
        self.listbox.configure(yscrollcommand=sb.set)

        # Önizleme
        pf = ctk.CTkFrame(left, fg_color=CARD, corner_radius=10, height=130)
        pf.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 4))
        pf.grid_propagate(False)
        pf.grid_columnconfigure(1, weight=1)
        pf.grid_rowconfigure(0, weight=1)

        self.preview_img_lbl = ctk.CTkLabel(
            pf, text="🖼", width=155, height=110,
            font=ctk.CTkFont("Segoe UI", 28), fg_color=BG,
            corner_radius=8, text_color=TEXT_MUTED)
        self.preview_img_lbl.grid(row=0, column=0, padx=(8, 0), pady=10, sticky="w")

        self.preview_info_lbl = ctk.CTkLabel(
            pf, text="Listeden bir dosya seçin\nveya sürükleyip bırakın",
            font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_DIM,
            anchor="nw", justify="left", wraplength=220)
        self.preview_info_lbl.grid(row=0, column=1, padx=12, pady=10, sticky="nw")

        # İlerleme
        pc = ctk.CTkFrame(left, fg_color=CARD, corner_radius=10)
        pc.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        pc.grid_columnconfigure(0, weight=1)

        pt = ctk.CTkFrame(pc, fg_color="transparent")
        pt.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        pt.grid_columnconfigure(0, weight=1)

        self.prog_lbl = ctk.CTkLabel(pt, text="Hazır",
                                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED)
        self.prog_lbl.grid(row=0, column=0, sticky="w")
        self.prog_pct = ctk.CTkLabel(pt, text="",
                                     font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
                                     text_color=ACCENT)
        self.prog_pct.grid(row=0, column=1, sticky="e")

        self.prog_bar = ctk.CTkProgressBar(pc, height=6, corner_radius=3,
                                           progress_color=ACCENT, fg_color="#2d3550")
        self.prog_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self.prog_bar.set(0)

        # Log
        ctk.CTkLabel(left, text="  📜  Log",
                     font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
                     text_color=TEXT_DIM).grid(row=5, column=0, columnspan=2,
                                               sticky="w", padx=10, pady=(4, 2))
        self.log_box = ctk.CTkTextbox(
            left, height=130, font=ctk.CTkFont("Consolas", 9),
            fg_color=CARD, text_color=TEXT_DIM, corner_radius=10)
        self.log_box.grid(row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))

    # ── Sağ Panel ──────────────────────────────────────────────────────────
    def _build_right(self):
        outer = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        outer.grid(row=0, column=1, padx=(6, 14), pady=14, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(0, weight=1)  # rp row

        self.rp = ctk.CTkScrollableFrame(outer, fg_color="transparent",
                                         scrollbar_button_color=ACCENT,
                                         scrollbar_button_hover_color=ACCENT_H)
        self.rp.grid(row=0, column=0, padx=6, pady=(6, 0), sticky="nsew")
        self.rp.grid_columnconfigure(0, weight=1)

        self._build_settings()

        # Footer: tema seçici + imza
        sig = ctk.CTkFrame(outer, fg_color="transparent")
        sig.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 8))
        sig.grid_columnconfigure(1, weight=1)

        self.theme_var = tk.StringVar(value="dark")
        self.theme_seg = ctk.CTkSegmentedButton(
            sig, values=_THEME_LABELS, command=self._on_theme_change,
            fg_color=CARD, selected_color=ACCENT, selected_hover_color=ACCENT_H,
            unselected_color=CARD, unselected_hover_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont("Segoe UI", 9), height=24,
        )
        self.theme_seg.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(sig, text="⚔  Lord Bener Ç.",
                     font=ctk.CTkFont("Segoe UI", 10, slant="italic"),
                     text_color="#3d2f6b", anchor="e").grid(row=0, column=1, sticky="e")

    def _card(self, row, padtop=4):
        f = ctk.CTkFrame(self.rp, fg_color=CARD, corner_radius=10)
        f.grid(row=row, column=0, sticky="ew", padx=2, pady=(padtop, 2))
        f.grid_columnconfigure(0, weight=1)
        return f

    def _sect(self, parent, text, row=0):
        ctk.CTkLabel(parent, text=text, font=ctk.CTkFont("Segoe UI", 9, weight="bold"),
                     text_color=TEXT_MUTED).grid(row=row, column=0,
                                                  sticky="w", padx=12, pady=(6, 3))

    def _slider_row(self, parent, row, label, var, lbl_ref_name, from_, to, steps, fmt="%d%%"):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", padx=10, pady=1)
        f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(f, text=label, width=88, font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM, anchor="w").grid(row=0, column=0, sticky="w")
        lbl = ctk.CTkLabel(f, text=fmt % var.get(), width=46,
                           font=ctk.CTkFont("Segoe UI", 11, weight="bold"), text_color=ACCENT)
        lbl.grid(row=0, column=2)
        setattr(self, lbl_ref_name, lbl)
        ctk.CTkSlider(f, from_=from_, to=to, variable=var, number_of_steps=steps,
                      height=14, button_color=ACCENT, button_hover_color=ACCENT_H,
                      progress_color=ACCENT, fg_color="#2d3550",
                      command=lambda v, l=lbl, fmts=fmt: l.configure(text=fmts % int(float(v))),
                      ).grid(row=0, column=1, sticky="ew", padx=8)

    def _build_settings(self):
        row = 0

        # ── Çıktı Klasörü ──────────────────────────────────────────────────
        c = self._card(row, padtop=0); row += 1
        self._sect(c, "📂  ÇIKTI KLASÖRÜ")
        of = ctk.CTkFrame(c, fg_color="transparent")
        of.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        of.grid_columnconfigure(0, weight=1)
        self.out_var = tk.StringVar(value=str(Path.home() / "Dönüştürülen"))
        ctk.CTkEntry(of, textvariable=self.out_var, corner_radius=8, height=34,
                     fg_color=BG, border_color=BORDER, text_color=TEXT,
                     ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(of, text="...", width=40, height=34, corner_radius=8,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.choose_output).grid(row=0, column=1)
        ctk.CTkButton(of, text="📂", width=40, height=34, corner_radius=8,
                      fg_color=CARD, hover_color="#252e48",
                      border_width=1, border_color=BORDER,
                      command=self.open_output).grid(row=0, column=2, padx=(6, 0))

        # ── Format ─────────────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "🎨  ÇIKTI FORMATI")
        self.fmt_var = ctk.StringVar(value="JPG")
        ff = ctk.CTkFrame(c, fg_color="transparent")
        ff.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        for i, fmt in enumerate(OUTPUT_FORMATS):
            ctk.CTkRadioButton(ff, text=fmt, variable=self.fmt_var, value=fmt,
                               command=self._on_format,
                               fg_color=ACCENT, hover_color=ACCENT_H,
                               text_color=TEXT).grid(row=0, column=i, padx=10)

        # ── Kalite ─────────────────────────────────────────────────────────
        self.q_card = self._card(row); row += 1
        self._sect(self.q_card, "🎚  KALİTE  (JPG / WEBP / AVIF)")
        self.q_var = tk.IntVar(value=85)
        self._slider_row(self.q_card, 1, "Kalite:", self.q_var, "q_lbl", 1, 100, 99)
        ctk.CTkFrame(self.q_card, height=4, fg_color="transparent").grid(row=2, column=0)

        # ── PNG Sıkıştırma ─────────────────────────────────────────────────
        self.png_card = self._card(row); row += 1
        self._sect(self.png_card, "🗜  PNG SIKIŞTIRILMA  (0 = hız · 9 = küçük dosya)")
        self.png_compress_var = tk.IntVar(value=6)
        self._slider_row(self.png_card, 1, "Seviye:", self.png_compress_var, "png_compress_lbl", 0, 9, 9, "%d")
        ctk.CTkFrame(self.png_card, height=4, fg_color="transparent").grid(row=2, column=0)

        # ── Boyutlandırma ──────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "📐  YENİDEN BOYUTLANDIRMA")
        self.resize_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(c, text="Yeniden boyutlandır", variable=self.resize_var,
                        command=self._on_resize, fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

        self.rs_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.rs_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))

        ctk.CTkLabel(self.rs_frame, text="Genişlik:", width=74,
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_DIM,
                     anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        self.w_var = tk.StringVar(value="1920")
        self.w_entry = ctk.CTkEntry(self.rs_frame, textvariable=self.w_var,
                                    width=84, height=30, corner_radius=8,
                                    fg_color=BG, border_color=BORDER, text_color=TEXT)
        self.w_entry.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=3)
        ctk.CTkLabel(self.rs_frame, text="px", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_MUTED).grid(row=0, column=2, padx=(4, 0))

        ctk.CTkLabel(self.rs_frame, text="Yükseklik:", width=74,
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_DIM,
                     anchor="w").grid(row=1, column=0, sticky="w", pady=3)
        self.h_var = tk.StringVar(value="1080")
        self.h_entry = ctk.CTkEntry(self.rs_frame, textvariable=self.h_var,
                                    width=84, height=30, corner_radius=8,
                                    fg_color=BG, border_color=BORDER, text_color=TEXT)
        self.h_entry.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=3)
        ctk.CTkLabel(self.rs_frame, text="px",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED,
                     ).grid(row=1, column=2, padx=(4, 0))

        self.w_var.trace_add("write", self._on_w_changed)
        self.h_var.trace_add("write", self._on_h_changed)

        self.ratio_var = tk.BooleanVar(value=True)
        self.ratio_cb = ctk.CTkCheckBox(
            self.rs_frame, text="En boy oranını koru",
            variable=self.ratio_var, command=self._on_ratio,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI", 11))
        self.ratio_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 4))
        ctk.CTkFrame(c, height=4, fg_color="transparent").grid(row=3, column=0)
        self._on_resize()

        # ── Görüntü Ayarları ───────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "🔆  GÖRÜNTÜ AYARLARI")
        self.brightness_var = tk.IntVar(value=100)
        self.contrast_var   = tk.IntVar(value=100)
        self.saturation_var = tk.IntVar(value=100)
        self._slider_row(c, 1, "Parlaklık:",  self.brightness_var, "brightness_lbl", 10, 200, 190)
        self._slider_row(c, 2, "Kontrast:",   self.contrast_var,   "contrast_lbl",   10, 200, 190)
        self._slider_row(c, 3, "Doygunluk:",  self.saturation_var, "saturation_lbl", 0,  200, 200)
        ctk.CTkFrame(c, height=4, fg_color="transparent").grid(row=4, column=0)

        # ── Döndürme ───────────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "🔄  DÖNDÜRME / AYNA")
        self.rotation_var = tk.StringVar(value="Yok")
        rf = ctk.CTkFrame(c, fg_color="transparent")
        rf.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        for i, opt in enumerate(ROTATION_OPTIONS):
            ctk.CTkRadioButton(rf, text=opt, variable=self.rotation_var, value=opt,
                               fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
                               font=ctk.CTkFont("Segoe UI", 10),
                               ).grid(row=i // 3, column=i % 3, sticky="w", padx=8, pady=2)

        # ── Filigran ───────────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "💧  FİLİGRAN")
        self.wm_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(c, text="Filigran ekle", variable=self.wm_enabled_var,
                        command=self._on_wm_toggle,
                        fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))

        self.wm_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.wm_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.wm_frame.grid_columnconfigure(1, weight=1)

        _ek = dict(height=30, corner_radius=8, fg_color=BG, border_color=BORDER, text_color=TEXT)
        ctk.CTkLabel(self.wm_frame, text="Metin:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=0, column=0, sticky="w", pady=3)
        self.wm_text_var = tk.StringVar()
        ctk.CTkEntry(self.wm_frame, textvariable=self.wm_text_var,
                     placeholder_text="ör.  © 2025 Bener",
                     **_ek).grid(row=0, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=3)

        ctk.CTkLabel(self.wm_frame, text="Konum:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=1, column=0, sticky="w", pady=3)
        self.wm_position_var = tk.StringVar(value="Sağ Alt")
        ctk.CTkComboBox(self.wm_frame, values=WM_POSITIONS, variable=self.wm_position_var,
                        width=130, height=30, corner_radius=8,
                        fg_color=BG, border_color=BORDER, text_color=TEXT,
                        button_color=ACCENT, button_hover_color=ACCENT_H,
                        dropdown_fg_color=CARD, dropdown_text_color=TEXT,
                        ).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=3)

        self.wm_size_var    = tk.IntVar(value=36)
        self.wm_opacity_var = tk.IntVar(value=160)
        self._slider_row(self.wm_frame, 2, "Boyut:", self.wm_size_var, "wm_size_lbl",
                         12, 120, 108, "%d")
        self._slider_row(self.wm_frame, 3, "Opaklık:", self.wm_opacity_var, "wm_opacity_lbl",
                         10, 255, 245, "%d")

        # ── Maksimum Dosya Boyutu ──────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "📦  MAKSİMUM DOSYA BOYUTU  (JPG / WEBP)")
        self.max_size_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(c, text="Boyutu sınırla", variable=self.max_size_var,
                        fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 4))
        mf = ctk.CTkFrame(c, fg_color="transparent")
        mf.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 10))
        ctk.CTkLabel(mf, text="Maks:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).pack(side="left")
        self.max_size_kb_var = tk.StringVar(value="500")
        ctk.CTkEntry(mf, textvariable=self.max_size_kb_var, width=72, height=30,
                     corner_radius=8, fg_color=BG, border_color=BORDER,
                     text_color=TEXT).pack(side="left", padx=(6, 4))
        ctk.CTkLabel(mf, text="KB", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_MUTED).pack(side="left")

        # ── Dosya Adı ──────────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "✏  DOSYA ADI")
        nf = ctk.CTkFrame(c, fg_color="transparent")
        nf.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        nf.grid_columnconfigure(1, weight=1)
        _entry_kw = dict(height=30, corner_radius=8, fg_color=BG, border_color=BORDER, text_color=TEXT)

        ctk.CTkLabel(nf, text="Önek:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=0, column=0, sticky="w", pady=(2, 0))
        self.pfx_var = tk.StringVar()
        ctk.CTkEntry(nf, textvariable=self.pfx_var, placeholder_text="ör.  tatil_",
                     **_entry_kw).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(2, 0))
        ctk.CTkLabel(nf, text="Sonek:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.sfx_var = tk.StringVar()
        ctk.CTkEntry(nf, textvariable=self.sfx_var, placeholder_text="ör.  _2024",
                     **_entry_kw).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))

        self.keepname_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(nf, text="Orijinal dosya adını koru", variable=self.keepname_var,
                        fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 3))
        self.num_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(nf, text="Numaralandır", variable=self.num_var,
                        command=self._on_num, fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)

        self.num_row = ctk.CTkFrame(nf, fg_color="transparent")
        self.num_row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ctk.CTkLabel(self.num_row, text="Başlangıç:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).pack(side="left")
        self.nstart_var = tk.StringVar(value="1")
        ctk.CTkEntry(self.num_row, textvariable=self.nstart_var, width=55, height=28,
                     corner_radius=8, fg_color=BG, border_color=BORDER,
                     text_color=TEXT).pack(side="left", padx=4)
        ctk.CTkLabel(self.num_row, text="Basamak:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).pack(side="left", padx=(10, 0))
        self.npad_var = tk.StringVar(value="3")
        ctk.CTkEntry(self.num_row, textvariable=self.npad_var, width=42, height=28,
                     corner_radius=8, fg_color=BG, border_color=BORDER,
                     text_color=TEXT).pack(side="left", padx=4)
        self._on_num()

        # ── Ek Seçenekler ──────────────────────────────────────────────────
        c = self._card(row); row += 1
        self._sect(c, "🔧  EK SEÇENEKLER")
        self.recursive_var = tk.BooleanVar(value=True)
        self.exif_var      = tk.BooleanVar(value=False)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.subfolder_var = tk.BooleanVar(value=False)
        self.minimize_tray_var = tk.BooleanVar(value=False)

        opts = [
            ("Alt klasörleri de tara",                self.recursive_var),
            ("EXIF verisini temizle (konum, kamera)", self.exif_var),
            ("Mevcut dosyaların üzerine yaz",         self.overwrite_var),
            ("Alt klasör yapısını çıktıda koru",      self.subfolder_var),
        ]
        if TRAY_SUPPORT:
            opts.append(("Kapatınca sistem tepsisine küçült", self.minimize_tray_var))

        for i, (t, v) in enumerate(opts):
            ctk.CTkCheckBox(c, text=t, variable=v,
                            fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
                            font=ctk.CTkFont("Segoe UI", 11),
                            ).grid(row=1 + i, column=0, sticky="w", padx=12, pady=3)

        wf = ctk.CTkFrame(c, fg_color="transparent")
        wf.grid(row=1 + len(opts), column=0, sticky="w", padx=12, pady=(6, 10))
        ctk.CTkLabel(wf, text="Paralel iş parçacığı:",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_DIM).pack(side="left")
        self.workers_var = tk.IntVar(value=4)
        workers_lbl = ctk.CTkLabel(wf, text="4", width=24,
                                   font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
                                   text_color=ACCENT)
        ctk.CTkSlider(wf, from_=1, to=16, variable=self.workers_var, number_of_steps=15,
                      width=100, height=14, button_color=ACCENT, button_hover_color=ACCENT_H,
                      progress_color=ACCENT, fg_color="#2d3550",
                      command=lambda v: workers_lbl.configure(text=str(int(float(v)))),
                      ).pack(side="left", padx=(8, 4))
        workers_lbl.pack(side="left")

        # ── Butonlar ───────────────────────────────────────────────────────
        self.conv_btn = ctk.CTkButton(
            self.rp, text="🚀  Dönüştür",
            height=52, corner_radius=12,
            font=ctk.CTkFont("Segoe UI", 16, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_H,
            command=self.start_conversion)
        self.conv_btn.grid(row=row, column=0, padx=2, pady=(12, 4), sticky="ew"); row += 1

        ctk.CTkButton(
            self.rp, text="🔍  Test Et (seçili dosyayı önizle)",
            height=36, corner_radius=10,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=CARD, hover_color="#252e48",
            border_width=1, border_color=BORDER, text_color=TEXT_DIM,
            command=self._test_preview,
        ).grid(row=row, column=0, padx=2, pady=(0, 4), sticky="ew"); row += 1

        self.cancel_btn = ctk.CTkButton(
            self.rp, text="⏹  Durdur",
            height=36, corner_radius=10,
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="#1f1520", hover_color="#2d1b2e",
            border_width=1, border_color="#5b2333", text_color=DANGER,
            command=self.cancel_conversion, state="disabled")
        self.cancel_btn.grid(row=row, column=0, padx=2, pady=(0, 10), sticky="ew")

    # ─────────────────────────── Olaylar ───────────────────────────────────
    def _on_theme_change(self, label: str = ""):
        if label:
            self.theme_var.set(_THEME_VALUES.get(label, "dark"))
        self._save_settings_from_ui()
        self.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def _on_format(self):
        fmt = self.fmt_var.get()
        if fmt == "PNG":
            self.q_card.grid_remove()
            self.png_card.grid()
        elif fmt in ("BMP", "TIFF"):
            self.q_card.grid_remove()
            self.png_card.grid_remove()
        else:
            self.png_card.grid_remove()
            self.q_card.grid()
        self.update_idletasks()

    def _on_w_changed(self, *_):
        if self._ratio_lock or not (self.resize_var.get() and self.ratio_var.get()):
            return
        try:
            w = int(self.w_var.get())
            if w > 0:
                self._ratio_lock = True
                self.h_var.set(str(max(1, round(w * self._ratio))))
        except (ValueError, tk.TclError):
            pass
        finally:
            self._ratio_lock = False

    def _on_h_changed(self, *_):
        if self._ratio_lock or not (self.resize_var.get() and self.ratio_var.get()):
            return
        try:
            h = int(self.h_var.get())
            if h > 0 and self._ratio > 0:
                self._ratio_lock = True
                self.w_var.set(str(max(1, round(h / self._ratio))))
        except (ValueError, ZeroDivisionError, tk.TclError):
            pass
        finally:
            self._ratio_lock = False

    def _on_resize(self):
        s = "normal" if self.resize_var.get() else "disabled"
        self.w_entry.configure(state=s)
        self.h_entry.configure(state=s)
        self.ratio_cb.configure(state=s)

    def _on_ratio(self):
        if self.ratio_var.get():
            try:
                w = int(self.w_var.get())
                h = int(self.h_var.get())
                if w > 0:
                    self._ratio = h / w
            except ValueError:
                pass

    def _on_num(self):
        s = "normal" if self.num_var.get() else "disabled"
        for w in self.num_row.winfo_children():
            try:
                w.configure(state=s)
            except Exception:
                pass

    def _on_wm_toggle(self):
        s = "normal" if self.wm_enabled_var.get() else "disabled"
        for child in self.wm_frame.winfo_children():
            try:
                child.configure(state=s)
            except Exception:
                pass

    # ─────────────────────────── Önizleme ──────────────────────────────────
    def _on_select(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        fp = self.files[sel[0]]
        try:
            img = Image.open(fp)
            orig_w, orig_h = img.size
            thumb = img.copy()
            thumb.thumbnail((150, 108))
            ctk_img = ctk.CTkImage(thumb, size=thumb.size)
            self.preview_img_lbl.configure(image=ctk_img, text="")
            self._preview_ref = ctk_img
            sz = self._sz(Path(fp).stat().st_size)
            fmt = Path(fp).suffix.upper().lstrip(".")
            self.preview_info_lbl.configure(
                text=f"{Path(fp).name}\n\n📐  {orig_w} × {orig_h} px\n💾  {sz}\n🏷  {fmt}")
        except Exception:
            self.preview_img_lbl.configure(image=None, text="❌")
            self.preview_info_lbl.configure(text="Önizleme oluşturulamadı")

    def _open_in_explorer(self, event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        fp = Path(self.files[sel[0]])
        if fp.exists():
            subprocess.run(["explorer", "/select,", str(fp)])

    # ─────────────────────────── Dosya Yönetimi ────────────────────────────
    def add_folder(self):
        folder = filedialog.askdirectory(title="Kaynak Klasör Seç")
        if not folder:
            return
        pattern = "**/*" if self.recursive_var.get() else "*"
        added = 0
        p = Path(folder)
        for ext in SUPPORTED_INPUT:
            for f in list(p.glob(pattern + ext)) + list(p.glob(pattern + ext.upper())):
                if str(f) not in self.files:
                    self.files.append(str(f))
                    self.listbox.insert(tk.END, str(f.relative_to(p)))
                    added += 1
        self._update_count()
        self.log(f"📂 {folder}  →  {added} dosya eklendi")

    def add_files(self):
        ft = "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif *.avif"
        if HEIC_SUPPORT:
            ft += " *.heic *.heif"
        files = filedialog.askopenfilenames(title="Dosya Seç",
                                            filetypes=[("Resim", ft), ("Tümü", "*.*")])
        added = 0
        for f in files:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert(tk.END, Path(f).name)
                added += 1
        self._update_count()
        self.log(f"🖼 {added} dosya eklendi")

    def clear_files(self):
        self.files.clear()
        self.listbox.delete(0, tk.END)
        self._update_count()
        self.prog_bar.set(0)
        self.prog_lbl.configure(text="Hazır")
        self.prog_pct.configure(text="")
        self.preview_img_lbl.configure(image=None, text="🖼")
        self.preview_info_lbl.configure(text="Listeden bir dosya seçin\nveya sürükleyip bırakın")
        self._preview_ref = None

    def _delete_selected(self, _event=None):
        for i in reversed(self.listbox.curselection()):
            self.listbox.delete(i)
            self.files.pop(i)
        self._update_count()

    def _right_click(self, event):
        idx = self.listbox.nearest(event.y)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(idx)
        menu = tk.Menu(self, tearoff=0, bg="#1e1e2e", fg="white",
                       activebackground=ACCENT, activeforeground="white")
        menu.add_command(label="🗑 Listeden Kaldır", command=self._delete_selected)
        menu.add_command(label="📂 Klasörde Göster", command=self._open_in_explorer)
        menu.tk_popup(event.x_root, event.y_root)

    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        added = 0
        for fp in files:
            p = Path(fp)
            if p.is_dir():
                for ext in SUPPORTED_INPUT:
                    for f in list(p.rglob("*" + ext)) + list(p.rglob("*" + ext.upper())):
                        if str(f) not in self.files:
                            self.files.append(str(f))
                            self.listbox.insert(tk.END, f.name)
                            added += 1
            elif p.suffix.lower() in SUPPORTED_INPUT:
                if str(p) not in self.files:
                    self.files.append(str(p))
                    self.listbox.insert(tk.END, p.name)
                    added += 1
        self._update_count()
        if added:
            self.log(f"🖱️ Sürükle-bırak: {added} dosya eklendi")

    def choose_output(self):
        d = filedialog.askdirectory(title="Çıktı Klasörü Seç")
        if d:
            self.out_var.set(d)

    def open_output(self):
        path = Path(self.out_var.get().strip())
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showinfo("Bilgi", "Klasör henüz oluşturulmamış.")

    def _update_count(self):
        self.count_lbl.configure(text=f"{len(self.files)} dosya")

    # ─────────────────────────── Toast ─────────────────────────────────────
    def _show_toast(self, title: str, msg: str):
        t = ctk.CTkToplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(fg_color=CARD)
        ctk.CTkFrame(t, height=3, fg_color=ACCENT, corner_radius=0).pack(fill="x")
        ctk.CTkLabel(t, text=title, font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
                     text_color=ACCENT).pack(padx=16, pady=(10, 2), anchor="w")
        ctk.CTkLabel(t, text=msg, font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_DIM,
                     wraplength=280, anchor="w", justify="left",
                     ).pack(padx=16, pady=(0, 14), anchor="w")
        t.update_idletasks()
        sw = t.winfo_screenwidth()
        sh = t.winfo_screenheight()
        t.geometry(f"+{sw - t.winfo_width() - 24}+{sh - t.winfo_height() - 64}")
        t.after(5000, t.destroy)

    # ─────────────────────────── Geçmiş ────────────────────────────────────
    def _show_history(self):
        history = load_history()
        d = ctk.CTkToplevel(self)
        d.title("Dönüştürme Geçmişi")
        d.geometry("560x420")
        d.configure(fg_color=BG)
        d.grab_set()

        ctk.CTkLabel(d, text="🕘  Dönüştürme Geçmişi",
                     font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
                     text_color=ACCENT).pack(padx=16, pady=(14, 6), anchor="w")

        tb = ctk.CTkTextbox(d, font=ctk.CTkFont("Consolas", 10),
                            fg_color=CARD, text_color=TEXT_DIM, corner_radius=10)
        tb.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        if not history:
            tb.insert("end", "Henüz kayıt yok.")
        else:
            for e in history:
                date   = e.get("date", "")[:19].replace("T", " ")
                fmt    = e.get("format", "?")
                ok     = e.get("ok", 0)
                skip   = e.get("skip", 0)
                err    = e.get("err", 0)
                ti     = e.get("total_in", 0)
                to_    = e.get("total_out", 0)
                out    = e.get("out_dir", "")
                saving = f"  {self._sz(ti)} → {self._sz(to_)}" if ti and to_ else ""
                tb.insert("end", f"[{date}]  {fmt:<5}  ✅{ok} ⏭{skip} ❌{err}{saving}\n"
                                 f"           → {out}\n\n")

        tb.configure(state="disabled")

        ctk.CTkButton(d, text="Kapat", fg_color=ACCENT, hover_color=ACCENT_H,
                      command=d.destroy).pack(pady=(0, 12))

    # ─────────────────────────── Test Önizleme ─────────────────────────────
    def _test_preview(self):
        sel = self.listbox.curselection()
        fp = self.files[sel[0]] if sel else (self.files[0] if self.files else None)
        if not fp:
            messagebox.showwarning("Uyarı", "Önce bir dosya ekleyin ya da seçin.")
            return

        fmt = self.fmt_var.get()
        pil_fmt = PIL_MAP[fmt]
        try:
            img = Image.open(fp)
        except Exception as e:
            messagebox.showerror("Hata", f"Dosya açılamadı:\n{e}")
            return

        img = convert_mode(img, pil_fmt)
        try:
            tw = int(self.w_var.get()) if self.resize_var.get() else None
            th = int(self.h_var.get()) if self.resize_var.get() else None
        except ValueError:
            tw = th = None

        result = apply_pipeline(
            img,
            do_resize=self.resize_var.get(), tw=tw, th=th, keep_ratio=self.ratio_var.get(),
            rotation=self.rotation_var.get(),
            brightness=self.brightness_var.get(),
            contrast=self.contrast_var.get(),
            saturation=self.saturation_var.get(),
            wm_enabled=self.wm_enabled_var.get(),
            wm_text=self.wm_text_var.get(),
            wm_opacity=self.wm_opacity_var.get(),
            wm_position=self.wm_position_var.get(),
            wm_size=self.wm_size_var.get(),
        )

        # Mode fix for final save
        result = convert_mode(result, pil_fmt)

        # Geçici dosyaya kaydet ve aç
        suffix = EXT_MAP[fmt]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tmp_path = tf.name

        kw: dict[str, Any] = {}
        if pil_fmt == "JPEG":
            kw["quality"] = self.q_var.get(); kw["optimize"] = True
        elif pil_fmt == "WEBP":
            kw["quality"] = self.q_var.get()
        elif pil_fmt == "PNG":
            kw["compress_level"] = self.png_compress_var.get()

        result.save(tmp_path, pil_fmt, **kw)
        os.startfile(tmp_path)
        self.log(f"🔍 Test önizleme açıldı: {Path(tmp_path).name}")

    # ─────────────────────────── Dönüştürme ────────────────────────────────
    def start_conversion(self):
        if not self.files:
            messagebox.showwarning("Uyarı", "Lütfen dönüştürülecek dosya ekleyin.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Uyarı", "Lütfen çıktı klasörü belirtin.")
            return
        self.cancel_flag = False
        self.conv_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        threading.Thread(target=self._do_convert, args=(out,), daemon=True).start()

    def cancel_conversion(self):
        self.cancel_flag = True
        self.log("⏹ İptal isteği gönderildi…")

    def _build_settings_snapshot(self, out_dir: str) -> ConversionSettings | None:
        """UI'dan ConversionSettings oluşturur; hata varsa None döner."""
        fmt     = self.fmt_var.get()
        pil_fmt = PIL_MAP[fmt]
        do_resize   = self.resize_var.get()
        max_size_on = self.max_size_var.get() and pil_fmt in ("JPEG", "WEBP")
        try:
            tw           = int(self.w_var.get()) if do_resize else None
            th           = int(self.h_var.get()) if do_resize else None
            nstart       = int(self.nstart_var.get())
            npad         = int(self.npad_var.get())
            max_size_b   = int(self.max_size_kb_var.get()) * 1024 if max_size_on else 0
        except ValueError:
            return None
        return ConversionSettings(
            fmt=fmt, pil_fmt=pil_fmt, out_ext=EXT_MAP[fmt],
            quality=self.q_var.get(), png_compress=self.png_compress_var.get(),
            do_resize=do_resize, tw=tw, th=th, keep_ratio=self.ratio_var.get(),
            rm_exif=self.exif_var.get(), overwrite=self.overwrite_var.get(),
            subfolder=self.subfolder_var.get(),
            prefix=self.pfx_var.get(), suffix=self.sfx_var.get(),
            keepname=self.keepname_var.get(), do_num=self.num_var.get(),
            nstart=nstart, npad=npad,
            rotation=self.rotation_var.get(),
            brightness=self.brightness_var.get(), contrast=self.contrast_var.get(),
            saturation=self.saturation_var.get(),
            wm_enabled=self.wm_enabled_var.get(), wm_text=self.wm_text_var.get(),
            wm_opacity=self.wm_opacity_var.get(), wm_position=self.wm_position_var.get(),
            wm_size=self.wm_size_var.get(),
            max_size_bytes=max_size_b,
            workers=max(1, self.workers_var.get()),
            files=list(self.files),
        )

    def _do_convert(self, out_dir: str) -> None:
        s = self._build_settings_snapshot(out_dir)
        if s is None:
            self.log("❌ Hata: geçersiz sayısal değer!")
            self.after(0, self._finish)
            return

        files_snap = s.files
        total      = len(files_snap)
        lock       = threading.Lock()
        counters: dict[str, int] = {"ok": 0, "err": 0, "skip": 0, "done": 0,
                                     "total_in": 0, "total_out": 0}

        def convert_one(args: tuple):
            i, fp = args
            if self.cancel_flag:
                return
            try:
                in_size  = Path(fp).stat().st_size
                dest_dir = Path(out_dir) / Path(fp).parent.name if s.subfolder else Path(out_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)

                stem = Path(fp).stem
                if s.do_num:
                    name = f"{s.prefix}{str(s.nstart + i).zfill(s.npad)}{s.suffix}{s.out_ext}"
                elif s.keepname:
                    name = f"{s.prefix}{stem}{s.suffix}{s.out_ext}"
                else:
                    name = f"{s.prefix}{i + 1:0{len(str(total))}}{s.suffix}{s.out_ext}"

                out_path = dest_dir / name
                if out_path.exists() and not s.overwrite:
                    with lock:
                        counters["skip"] += 1
                        counters["done"] += 1
                    self.log(f"⏭ Atlandı (var): {name}")
                    self._update_progress(counters["done"], total)
                    return

                img = Image.open(fp)
                img = convert_mode(img, s.pil_fmt)
                img = apply_pipeline(
                    img,
                    do_resize=s.do_resize, tw=s.tw, th=s.th, keep_ratio=s.keep_ratio,
                    rotation=s.rotation, brightness=s.brightness,
                    contrast=s.contrast, saturation=s.saturation,
                    wm_enabled=s.wm_enabled, wm_text=s.wm_text,
                    wm_opacity=s.wm_opacity, wm_position=s.wm_position, wm_size=s.wm_size,
                )
                img = convert_mode(img, s.pil_fmt)  # watermark RGBA → RGB

                kw: dict[str, Any] = {}
                if s.pil_fmt == "JPEG":
                    kw["quality"] = s.quality; kw["optimize"] = True
                    if s.rm_exif:
                        kw["exif"] = b""
                elif s.pil_fmt == "WEBP":
                    kw["quality"] = s.quality
                    if s.rm_exif:
                        kw["exif"] = b""
                elif s.pil_fmt == "AVIF":
                    kw["quality"] = s.quality
                elif s.pil_fmt == "PNG":
                    kw["optimize"] = True; kw["compress_level"] = s.png_compress

                # Maksimum boyut kontrolü (JPEG / WEBP)
                if s.max_size_bytes > 0:
                    q = kw.get("quality", s.quality)
                    while q > 10:
                        buf = io.BytesIO()
                        img.save(buf, s.pil_fmt, **{**kw, "quality": q})
                        if buf.tell() <= s.max_size_bytes:
                            break
                        q -= 5
                    kw["quality"] = q

                img.save(out_path, s.pil_fmt, **kw)
                out_size = out_path.stat().st_size
                with lock:
                    counters["ok"]        += 1
                    counters["done"]      += 1
                    counters["total_in"]  += in_size
                    counters["total_out"] += out_size
                self.log(f"✅ {name}  ({self._sz(out_size)})")

            except Exception as e:
                with lock:
                    counters["err"]  += 1
                    counters["done"] += 1
                self.log(f"❌ {Path(fp).name}: {e}")

            self._update_progress(counters["done"], total)

        with ThreadPoolExecutor(max_workers=s.workers) as ex:
            ex.map(convert_one, enumerate(files_snap))

        ok        = counters["ok"]
        err       = counters["err"]
        skip      = counters["skip"]
        total_in  = counters["total_in"]
        total_out = counters["total_out"]

        durum = "tamamlandı 🎉" if not self.cancel_flag else "iptal edildi ⏹"
        self.log(f"\n{'─' * 44}")
        self.log(f"Dönüştürme {durum}  |  ✅ {ok}  ⏭ {skip}  ❌ {err}")

        if total_in > 0 and total_out > 0:
            diff     = total_in - total_out
            sign     = "↓" if diff >= 0 else "↑"
            pct_diff = abs(diff) / total_in * 100
            self.log(f"📊 Boyut: {self._sz(total_in)} → {self._sz(total_out)}"
                     f"  ({sign} {pct_diff:.1f}%  /  {self._sz(abs(diff))} tasarruf)")

        # Geçmişe kaydet
        append_history(HistoryEntry(
            date=datetime.now().isoformat(),
            fmt=s.fmt, ok=ok, skip=skip, err=err,
            out_dir=out_dir, total_in=total_in, total_out=total_out,
        ).to_dict())

        final_pct = 1.0 if not self.cancel_flag else counters["done"] / total
        self.after(0, self.prog_bar.set, final_pct)
        self.after(0, self.prog_pct.configure,
                   {"text": "100%" if not self.cancel_flag else ""})
        self.after(0, self.prog_lbl.configure,
                   {"text": f"{'Tamamlandı' if not self.cancel_flag else 'İptal'}"
                            f"  —  ✅{ok}  ⏭{skip}  ❌{err}"})
        self.after(0, self._finish, ok, err, skip)

    def _update_progress(self, done: int, total: int):
        pct = done / total
        self.after(0, self.prog_bar.set, pct)
        self.after(0, self.prog_pct.configure, {"text": f"%{int(pct * 100)}"})

    def _finish(self, ok=0, err=0, skip=0):
        self.conv_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        if ok > 0:
            self._show_toast(
                "✅  Dönüştürme Tamamlandı",
                f"{ok} dosya başarıyla dönüştürüldü."
                + (f"\n⏭ {skip} atlandı" if skip else "")
                + (f"\n❌ {err} hata" if err else ""),
            )

    # ─────────────────────────── Yardımcılar ───────────────────────────────
    def log(self, msg: str):
        def _ins():
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert(tk.END, f"[{ts}]  {msg}\n")
            self.log_box.see(tk.END)
        self.after(0, _ins)

    @staticmethod
    def _sz(b: int) -> str:
        return f"{b / 1024:.1f} KB" if b < 1_048_576 else f"{b / 1048576:.1f} MB"


if __name__ == "__main__":
    app = ImageConverter()
    app.mainloop()
