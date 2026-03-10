import os
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Obsidian Renk Paleti ───────────────────────────────────────────────────
BG         = "#0d1117"
SURFACE    = "#13171f"
CARD       = "#1c2132"
ACCENT     = "#7c3aed"
ACCENT_H   = "#6d28d9"
ACCENT2    = "#4f46e5"
TEXT       = "#e2e8f0"
TEXT_DIM   = "#94a3b8"
TEXT_MUTED = "#64748b"
SUCCESS    = "#10b981"
DANGER     = "#dc2626"
BORDER     = "#2d3550"

SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
EXT_MAP = {"JPG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
PIL_MAP = {"JPG": "JPEG", "PNG": "PNG", "WEBP": "WEBP"}


class ImageConverter(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self):
        super().__init__()
        self.TkdndVersion = TkinterDnD._require(self)
        self.configure(fg_color=BG)
        self.title("Görsel Dönüştürücü")
        self.geometry("1240x860")
        self.minsize(960, 700)
        self.files: list[str] = []
        self.cancel_flag = False
        self._ratio: float = 1080.0 / 1920.0
        self._ratio_lock: bool = False
        self._preview_ref = None
        self._build_ui()

    # ─────────────────────────── UI ────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    # ── Sol Panel ──────────────────────────────────────────────────────────
    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        left.grid(row=0, column=0, padx=(14, 6), pady=14, sticky="nsew")
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # count_lbl (gizli, _update_count için)
        self.count_lbl = ctk.CTkLabel(left, text="0 dosya",
                                      font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED)

        # Toolbar
        tb = ctk.CTkFrame(left, fg_color="transparent")
        tb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 4))

        _btn = dict(height=34, corner_radius=8, font=ctk.CTkFont("Segoe UI", 12))
        ctk.CTkButton(tb, text="📂  Klasör", width=110,
                      fg_color=ACCENT, hover_color=ACCENT_H,
                      command=self.add_folder, **_btn).pack(side="left", padx=(0, 4))
        ctk.CTkButton(tb, text="🖼  Dosya", width=100,
                      fg_color=CARD, hover_color="#252e48",
                      border_width=1, border_color=BORDER,
                      command=self.add_files, **_btn).pack(side="left", padx=4)
        ctk.CTkButton(tb, text="🗑  Temizle", width=95,
                      fg_color="#1f1520", hover_color="#2d1b2e",
                      border_width=1, border_color="#5b2333", text_color=DANGER,
                      command=self.clear_files, **_btn).pack(side="left", padx=4)

        # Dosya listesi
        lf = ctk.CTkFrame(left, fg_color=CARD, corner_radius=10)
        lf.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=2)
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            lf, bg=CARD, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#fff",
            font=("Consolas", 10), borderwidth=0, highlightthickness=0, activestyle="none",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.listbox.bind("<Delete>", self._delete_selected)
        self.listbox.bind("<Button-3>", self._right_click)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Drag & drop
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind("<<Drop>>", self._on_drop)

        sb = ctk.CTkScrollbar(lf, command=self.listbox.yview,
                              button_color=ACCENT, button_hover_color=ACCENT_H)
        sb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 4))
        self.listbox.configure(yscrollcommand=sb.set)

        # ── Önizleme ──────────────────────────────────────────────────────
        pf = ctk.CTkFrame(left, fg_color=CARD, corner_radius=10, height=130)
        pf.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 4))
        pf.grid_propagate(False)
        pf.grid_columnconfigure(1, weight=1)
        pf.grid_rowconfigure(0, weight=1)

        self.preview_img_lbl = ctk.CTkLabel(
            pf, text="🖼", width=155, height=110,
            font=ctk.CTkFont("Segoe UI", 28), fg_color=BG,
            corner_radius=8, text_color=TEXT_MUTED,
        )
        self.preview_img_lbl.grid(row=0, column=0, padx=(8, 0), pady=10, sticky="w")

        self.preview_info_lbl = ctk.CTkLabel(
            pf, text="Listeden bir dosya seçin\nveya sürükleyip bırakın",
            font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_DIM,
            anchor="nw", justify="left", wraplength=220,
        )
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
            fg_color=CARD, text_color=TEXT_DIM, corner_radius=10,
        )
        self.log_box.grid(row=6, column=0, columnspan=2, sticky="ew",
                          padx=10, pady=(0, 10))

    # ── Sağ Panel ──────────────────────────────────────────────────────────
    def _build_right(self):
        outer = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=14)
        outer.grid(row=0, column=1, padx=(6, 14), pady=14, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # Scrollable alan
        self.rp = ctk.CTkScrollableFrame(outer, fg_color="transparent",
                                         scrollbar_button_color=ACCENT,
                                         scrollbar_button_hover_color=ACCENT_H)
        self.rp.grid(row=0, column=0, padx=6, pady=(6, 2), sticky="nsew")
        self.rp.grid_columnconfigure(0, weight=1)

        self._build_settings()

        # İmza
        sig = ctk.CTkFrame(outer, fg_color="transparent")
        sig.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        sig.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sig, text="⚔  Lord Bener Ç.",
            font=ctk.CTkFont("Segoe UI", 10, slant="italic"),
            text_color="#3d2f6b",
            anchor="e",
        ).grid(row=0, column=0, sticky="e")

    def _card(self, row, padtop=4):
        f = ctk.CTkFrame(self.rp, fg_color=CARD, corner_radius=10)
        f.grid(row=row, column=0, sticky="ew", padx=2, pady=(padtop, 2))
        f.grid_columnconfigure(0, weight=1)
        return f

    def _sect(self, parent, text, row=0):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 9, weight="bold"),
                     text_color=TEXT_MUTED).grid(row=row, column=0,
                                                  sticky="w", padx=12, pady=(10, 6))

    def _build_settings(self):
        # ── Çıktı Klasörü ──────────────────────────────────────────────────
        c0 = self._card(0, padtop=0)
        self._sect(c0, "📂  ÇIKTI KLASÖRÜ")
        of = ctk.CTkFrame(c0, fg_color="transparent")
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
        c1 = self._card(1)
        self._sect(c1, "🎨  ÇIKTI FORMATI")
        self.fmt_var = ctk.StringVar(value="JPG")
        ff = ctk.CTkFrame(c1, fg_color="transparent")
        ff.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        for i, fmt in enumerate(["JPG", "PNG", "WEBP"]):
            ctk.CTkRadioButton(ff, text=fmt, variable=self.fmt_var, value=fmt,
                               command=self._on_format,
                               fg_color=ACCENT, hover_color=ACCENT_H,
                               text_color=TEXT).grid(row=0, column=i, padx=14)

        # ── Kalite (PNG seçilince kaybolur) ────────────────────────────────
        self.q_card = self._card(2)
        self._sect(self.q_card, "🎚  KALİTE")
        qf = ctk.CTkFrame(self.q_card, fg_color="transparent")
        qf.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        qf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(qf, text="Kalite:", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=0, column=0, sticky="w")
        self.q_var = tk.IntVar(value=85)
        self.q_lbl = ctk.CTkLabel(qf, text="85%", width=42,
                                   font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
                                   text_color=ACCENT)
        self.q_lbl.grid(row=0, column=2)
        ctk.CTkSlider(qf, from_=1, to=100, variable=self.q_var, number_of_steps=99,
                      height=16, button_color=ACCENT, button_hover_color=ACCENT_H,
                      progress_color=ACCENT, fg_color="#2d3550",
                      command=lambda v: self.q_lbl.configure(text=f"{int(float(v))}%"),
                      ).grid(row=0, column=1, sticky="ew", padx=8)

        # ── Boyutlandırma ──────────────────────────────────────────────────
        c3 = self._card(3)
        self._sect(c3, "📐  YENİDEN BOYUTLANDIRMA")
        self.resize_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(c3, text="Yeniden boyutlandır", variable=self.resize_var,
                        command=self._on_resize, fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))

        self.rs_frame = ctk.CTkFrame(c3, fg_color="transparent")
        self.rs_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
        self.rs_frame.grid_columnconfigure(1, weight=0)

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
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED
                     ).grid(row=1, column=2, padx=(4, 0))

        self.w_var.trace_add("write", self._on_w_changed)
        self.h_var.trace_add("write", self._on_h_changed)

        self.ratio_var = tk.BooleanVar(value=True)
        self.ratio_cb = ctk.CTkCheckBox(
            self.rs_frame, text="En boy oranını koru  (biri değişince diğeri otomatik güncellenir)",
            variable=self.ratio_var, command=self._on_ratio,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI", 11),
        )
        self.ratio_cb.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 4))
        ctk.CTkFrame(c3, height=4, fg_color="transparent").grid(row=3, column=0)
        self._on_resize()

        # ── Dosya Adı ──────────────────────────────────────────────────────
        c4 = self._card(4)
        self._sect(c4, "✏  DOSYA ADI")
        nf = ctk.CTkFrame(c4, fg_color="transparent")
        nf.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        nf.grid_columnconfigure(1, weight=1)

        _entry_kw = dict(height=30, corner_radius=8,
                         fg_color=BG, border_color=BORDER, text_color=TEXT)

        ctk.CTkLabel(nf, text="Önek (Prefix):", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=0, column=0, sticky="w", pady=(2, 0))
        self.pfx_var = tk.StringVar()
        ctk.CTkEntry(nf, textvariable=self.pfx_var, placeholder_text="ör.  tatil_",
                     **_entry_kw).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(2, 0))
        ctk.CTkLabel(nf, text="Dosya adının BAŞINA eklenir  →  tatil_foto.jpg",
                     font=ctk.CTkFont("Segoe UI", 9), text_color=TEXT_MUTED,
                     ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(1, 8))

        ctk.CTkLabel(nf, text="Sonek (Suffix):", font=ctk.CTkFont("Segoe UI", 11),
                     text_color=TEXT_DIM).grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.sfx_var = tk.StringVar()
        ctk.CTkEntry(nf, textvariable=self.sfx_var, placeholder_text="ör.  _2024",
                     **_entry_kw).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(2, 0))
        ctk.CTkLabel(nf, text="Uzantıdan önce SONA eklenir  →  foto_2024.jpg",
                     font=ctk.CTkFont("Segoe UI", 9), text_color=TEXT_MUTED,
                     ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(1, 8))

        self.keepname_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(nf, text="Orijinal dosya adını koru",
                        variable=self.keepname_var,
                        fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=4, column=0, columnspan=2,
                                              sticky="w", pady=3)

        self.num_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(nf, text="Numaralandır", variable=self.num_var,
                        command=self._on_num,
                        fg_color=ACCENT, hover_color=ACCENT_H,
                        text_color=TEXT).grid(row=5, column=0, columnspan=2,
                                              sticky="w", pady=3)

        self.num_row = ctk.CTkFrame(nf, fg_color="transparent")
        self.num_row.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        ctk.CTkLabel(self.num_row, text="Başlangıç:",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_DIM).pack(side="left")
        self.nstart_var = tk.StringVar(value="1")
        ctk.CTkEntry(self.num_row, textvariable=self.nstart_var,
                     width=55, height=28, corner_radius=8,
                     fg_color=BG, border_color=BORDER, text_color=TEXT).pack(side="left", padx=4)
        ctk.CTkLabel(self.num_row, text="Basamak:",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_DIM).pack(side="left", padx=(10, 0))
        self.npad_var = tk.StringVar(value="3")
        ctk.CTkEntry(self.num_row, textvariable=self.npad_var,
                     width=42, height=28, corner_radius=8,
                     fg_color=BG, border_color=BORDER, text_color=TEXT).pack(side="left", padx=4)
        self._on_num()

        # ── Ek Seçenekler ──────────────────────────────────────────────────
        c5 = self._card(5)
        self._sect(c5, "🔧  EK SEÇENEKLER")
        self.recursive_var = tk.BooleanVar(value=True)
        self.exif_var      = tk.BooleanVar(value=False)
        self.overwrite_var = tk.BooleanVar(value=False)
        self.subfolder_var = tk.BooleanVar(value=False)
        opts = [
            ("Alt klasörleri de tara",                self.recursive_var),
            ("EXIF verisini temizle (konum, kamera)", self.exif_var),
            ("Mevcut dosyaların üzerine yaz",         self.overwrite_var),
            ("Alt klasör yapısını çıktıda koru",      self.subfolder_var),
        ]
        for i, (t, v) in enumerate(opts):
            ctk.CTkCheckBox(c5, text=t, variable=v,
                            fg_color=ACCENT, hover_color=ACCENT_H, text_color=TEXT,
                            font=ctk.CTkFont("Segoe UI", 11),
                            ).grid(row=1 + i, column=0, sticky="w", padx=12, pady=3)
        ctk.CTkFrame(c5, height=8, fg_color="transparent").grid(row=10, column=0)

        # ── Dönüştür Butonu ────────────────────────────────────────────────
        self.conv_btn = ctk.CTkButton(
            self.rp, text="🚀  Dönüştür",
            height=52, corner_radius=12,
            font=ctk.CTkFont("Segoe UI", 16, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_H,
            command=self.start_conversion,
        )
        self.conv_btn.grid(row=6, column=0, padx=2, pady=(12, 4), sticky="ew")

        self.cancel_btn = ctk.CTkButton(
            self.rp, text="⏹  Durdur",
            height=36, corner_radius=10,
            font=ctk.CTkFont("Segoe UI", 13),
            fg_color="#1f1520", hover_color="#2d1b2e",
            border_width=1, border_color="#5b2333", text_color=DANGER,
            command=self.cancel_conversion, state="disabled",
        )
        self.cancel_btn.grid(row=7, column=0, padx=2, pady=(0, 10), sticky="ew")

    # ─────────────────────────── Olaylar ───────────────────────────────────
    def _on_format(self):
        if self.fmt_var.get() == "PNG":
            self.q_card.grid_remove()
        else:
            self.q_card.grid(row=2, column=0, sticky="ew", padx=2, pady=(4, 2))
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
        enabled = self.resize_var.get()
        state = "normal" if enabled else "disabled"
        self.w_entry.configure(state=state)
        self.h_entry.configure(state=state)
        self.ratio_cb.configure(state=state)

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
        state = "normal" if self.num_var.get() else "disabled"
        for w in self.num_row.winfo_children():
            try:
                w.configure(state=state)
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
            sz = self._sz(Path(fp))
            fmt = Path(fp).suffix.upper().lstrip(".")
            self.preview_info_lbl.configure(
                text=f"{Path(fp).name}\n\n📐  {orig_w} × {orig_h} px\n💾  {sz}\n🏷  {fmt}"
            )
        except Exception:
            self.preview_img_lbl.configure(image=None, text="❌")
            self.preview_info_lbl.configure(text="Önizleme oluşturulamadı")

    # ─────────────────────────── Dosya Yönetimi ────────────────────────────
    def add_folder(self):
        folder = filedialog.askdirectory(title="Kaynak Klasör Seç")
        if not folder:
            return
        pattern = "**/*" if self.recursive_var.get() else "*"
        added = 0
        p = Path(folder)
        for ext in SUPPORTED_FORMATS:
            for f in list(p.glob(pattern + ext)) + list(p.glob(pattern + ext.upper())):
                if str(f) not in self.files:
                    self.files.append(str(f))
                    self.listbox.insert(tk.END, str(f.relative_to(p)))
                    added += 1
        self._update_count()
        self.log(f"📂 {folder}  →  {added} dosya eklendi")

    def add_files(self):
        files = filedialog.askopenfilenames(
            title="Dosya Seç",
            filetypes=[("Resim", "*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tiff *.tif"),
                       ("Tümü", "*.*")])
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
        menu.tk_popup(event.x_root, event.y_root)

    def _on_drop(self, event):
        files = self.tk.splitlist(event.data)
        added = 0
        for fp in files:
            p = Path(fp)
            if p.is_dir():
                for ext in SUPPORTED_FORMATS:
                    for f in list(p.rglob("*" + ext)) + list(p.rglob("*" + ext.upper())):
                        if str(f) not in self.files:
                            self.files.append(str(f))
                            self.listbox.insert(tk.END, f.name)
                            added += 1
            elif p.suffix.lower() in SUPPORTED_FORMATS:
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

    # ─────────────────────────── Toast Bildirimi ───────────────────────────
    def _show_toast(self, title: str, msg: str):
        t = ctk.CTkToplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(fg_color=CARD)
        ctk.CTkFrame(t, height=3, fg_color=ACCENT, corner_radius=0).pack(fill="x")
        ctk.CTkLabel(t, text=title,
                     font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
                     text_color=ACCENT).pack(padx=16, pady=(10, 2), anchor="w")
        ctk.CTkLabel(t, text=msg,
                     font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_DIM,
                     wraplength=280, anchor="w", justify="left",
                     ).pack(padx=16, pady=(0, 14), anchor="w")
        t.update_idletasks()
        sw = t.winfo_screenwidth()
        sh = t.winfo_screenheight()
        t.geometry(f"+{sw - t.winfo_width() - 24}+{sh - t.winfo_height() - 64}")
        t.after(5000, t.destroy)

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

    def _do_convert(self, out_dir: str):
        fmt        = self.fmt_var.get()
        quality    = self.q_var.get()
        do_resize  = self.resize_var.get()
        keep_ratio = self.ratio_var.get()
        rm_exif    = self.exif_var.get()
        overwrite  = self.overwrite_var.get()
        prefix     = self.pfx_var.get()
        suffix     = self.sfx_var.get()
        keepname   = self.keepname_var.get()
        do_num     = self.num_var.get()
        out_ext    = EXT_MAP[fmt]
        pil_fmt    = PIL_MAP[fmt]

        try:
            nstart = int(self.nstart_var.get())
            npad   = int(self.npad_var.get())
            tw     = int(self.w_var.get()) if do_resize else None
            th     = int(self.h_var.get()) if do_resize else None
        except ValueError:
            self.log("❌ Hata: geçersiz sayısal değer!")
            self.after(0, self._finish)
            return

        total = len(self.files)
        ok = err = skip = 0
        total_in = 0
        total_out = 0

        for i, fp in enumerate(self.files):
            if self.cancel_flag:
                break

            pct = i / total
            self.after(0, self.prog_bar.set, pct)
            self.after(0, self.prog_pct.configure, {"text": f"%{int(pct * 100)}"})
            self.after(0, self.prog_lbl.configure,
                       {"text": f"{i + 1}/{total}  —  {Path(fp).name}"})

            try:
                total_in += Path(fp).stat().st_size
                dest_dir = Path(out_dir)
                dest_dir.mkdir(parents=True, exist_ok=True)

                stem = Path(fp).stem
                if do_num:
                    name = f"{prefix}{str(nstart + i).zfill(npad)}{suffix}{out_ext}"
                elif keepname:
                    name = f"{prefix}{stem}{suffix}{out_ext}"
                else:
                    name = f"{prefix}{i + 1:0{len(str(total))}}{suffix}{out_ext}"

                out_path = dest_dir / name
                if out_path.exists() and not overwrite:
                    self.log(f"⏭ Atlandı (var): {name}")
                    skip += 1
                    continue

                img = Image.open(fp)

                if pil_fmt in ("JPEG", "WEBP") and img.mode not in ("RGB", "L"):
                    if img.mode in ("RGBA", "LA", "P"):
                        img = img.convert("RGBA") if img.mode == "P" else img
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        bg.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
                        img = bg
                    else:
                        img = img.convert("RGB")
                elif img.mode not in ("RGB", "RGBA", "L"):
                    img = img.convert("RGB")

                if do_resize and tw:
                    if keep_ratio:
                        ratio = img.height / img.width
                        new_w = tw
                        new_h = max(1, int(new_w * ratio))
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                    else:
                        img = img.resize((tw, th), Image.LANCZOS)

                kw: dict = {}
                if pil_fmt == "JPEG":
                    kw["quality"] = quality
                    kw["optimize"] = True
                    if rm_exif:
                        kw["exif"] = b""
                elif pil_fmt == "WEBP":
                    kw["quality"] = quality
                    if rm_exif:
                        kw["exif"] = b""
                elif pil_fmt == "PNG":
                    kw["optimize"] = True

                img.save(out_path, pil_fmt, **kw)
                total_out += out_path.stat().st_size
                ok += 1
                self.log(f"✅ {name}  ({self._sz(out_path)})")

            except Exception as e:
                err += 1
                self.log(f"❌ {Path(fp).name}: {e}")

        final_pct = 1.0 if not self.cancel_flag else i / total
        self.after(0, self.prog_bar.set, final_pct)
        self.after(0, self.prog_pct.configure,
                   {"text": "100%" if not self.cancel_flag else ""})
        durum = "tamamlandı 🎉" if not self.cancel_flag else "iptal edildi ⏹"
        self.log(f"\n{'─' * 44}")
        self.log(f"Dönüştürme {durum}  |  ✅ {ok}  ⏭ {skip}  ❌ {err}")

        # Boyut karşılaştırması
        if total_in > 0 and total_out > 0:
            diff = total_in - total_out
            sign = "↓" if diff >= 0 else "↑"
            pct_diff = abs(diff) / total_in * 100
            self.log(f"📊 Boyut: {self._sz_b(total_in)} → {self._sz_b(total_out)}"
                     f"  ({sign} {pct_diff:.1f}%  /  {self._sz_b(abs(diff))} tasarruf)")

        self.after(0, self.prog_lbl.configure,
                   {"text": f"{'Tamamlandı' if not self.cancel_flag else 'İptal'}"
                            f"  —  ✅{ok}  ⏭{skip}  ❌{err}"})
        self.after(0, self._finish, ok, err, skip)

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
    def _sz(path: Path) -> str:
        b = path.stat().st_size
        return f"{b / 1024:.1f} KB" if b < 1_048_576 else f"{b / 1048576:.1f} MB"

    @staticmethod
    def _sz_b(b: int) -> str:
        return f"{b / 1024:.1f} KB" if b < 1_048_576 else f"{b / 1048576:.1f} MB"


if __name__ == "__main__":
    app = ImageConverter()
    app.mainloop()
