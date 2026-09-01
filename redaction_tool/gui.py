"""Tkinter desktop GUI for the FERPA/HIPAA Redaction Tool.

Workflow:
  1. Add documents (PDF / DOCX / XLSX) — open dialog or drag & drop.
  2. Pick a redaction preset (built-in FERPA / HIPAA / Full, or custom) and
     optionally add literal texts (e.g. known subject names) or regexes.
  3. Scan to preview how many items would be redacted per category.
  4. Redact — writes permanent redacted copies (never touches originals).

Supports light and dark themes (toggle in the header; choice is remembered
in ~/.redaction_tool/settings.json).
"""

from __future__ import annotations

import json
import os
import queue
import secrets
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import detector, ocr, presets, redactor

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND_OK = True
except Exception:  # pragma: no cover - drag & drop is optional
    _DND_OK = False

# ── themes ─────────────────────────────────────────────────────────────────

THEMES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#f4f6f8",
        "fg": "#111827",
        "muted": "#6b7280",
        "faint": "#9ca3af",
        "surface": "#ffffff",
        "accent": "#2563eb",
        "accent_hover": "#1d4ed8",
        "danger": "#b91c1c",
        "danger_hover": "#991b1b",
        "purple": "#7c3aed",
        "purple_hover": "#6d28d9",
        "green": "#16a34a",
        "green_hover": "#15803d",
        "gray_btn": "#6b7280",
        "gray_btn_hover": "#4b5563",
        "plain_btn": "#e5e7eb",
        "statusbar": "#e5e7eb",
        "entry_bg": "#ffffff",
    },
    "dark": {
        "bg": "#1e2330",
        "fg": "#e5e7eb",
        "muted": "#9ca3af",
        "faint": "#6b7280",
        "surface": "#2a3142",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "danger": "#dc2626",
        "danger_hover": "#b91c1b",
        "purple": "#8b5cf6",
        "purple_hover": "#7c3aed",
        "green": "#22c55e",
        "green_hover": "#16a34a",
        "gray_btn": "#4b5563",
        "gray_btn_hover": "#6b7280",
        "plain_btn": "#374151",
        "statusbar": "#141824",
        "entry_bg": "#141824",
    },
}

_SETTINGS_PATH = presets._presets_dir().parent / "settings.json"

FILE_TYPES = [
    ("All supported", "*.pdf *.docx *.xlsx *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
    ("Documents", "*.pdf *.docx *.xlsx"),
    ("PDF files", "*.pdf"),
    ("Word documents", "*.docx"),
    ("Excel workbooks", "*.xlsx"),
    ("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
    ("All files", "*.*"),
]


def _load_theme() -> str:
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
        if data.get("theme") in THEMES:
            return data["theme"]
    except Exception:
        pass
    return "light"


def _save_theme(name: str) -> None:
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps({"theme": name}), encoding="utf-8")
    except Exception:
        pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Redaction Tool — FERPA / HIPAA")
        self.root.geometry("860x740")
        self.root.minsize(760, 660)

        self.theme_name = _load_theme()
        self.t = THEMES[self.theme_name]

        self.files: list[str] = []
        self.last_outputs: list[Path] = []
        self._batch_queue: queue.Queue | None = None
        self._build_ui()
        self._bind_dnd(root)
        self._apply_theme()

    # ------------------------------------------------------------- theming
    def toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.t = THEMES[self.theme_name]
        _save_theme(self.theme_name)
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self.t
        self.root.configure(bg=t["bg"])
        self.theme_btn.configure(
            text="☀ Light mode" if self.theme_name == "dark" else "🌙 Dark mode")
        self._style_ttk()
        self._walk(self.root)

    def _style_ttk(self) -> None:
        t = self.t
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")  # clam honors custom colors
        except tk.TclError:
            pass
        style.configure("TCombobox",
                        fieldbackground=t["entry_bg"], background=t["entry_bg"],
                        foreground=t["fg"], arrowcolor=t["fg"],
                        bordercolor=t["muted"], lightcolor=t["entry_bg"],
                        darkcolor=t["entry_bg"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", t["entry_bg"])],
                  foreground=[("readonly", t["fg"])],
                  selectbackground=[("readonly", t["entry_bg"])],
                  selectforeground=[("readonly", t["fg"])])
        # The dropdown listbox of a combobox:
        self.root.option_add("*TCombobox*Listbox.background", t["surface"])
        self.root.option_add("*TCombobox*Listbox.foreground", t["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", t["accent"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def _walk(self, widget: tk.Widget) -> None:
        t = self.t
        for w in widget.winfo_children():
            role = getattr(w, "_theme_role", None)
            cls = w.winfo_class()
            try:
                if cls == "Frame":
                    w.configure(bg=t["bg"])
                elif cls == "Label":
                    fg = {"muted": t["muted"], "faint": t["faint"]}.get(role, t["fg"])
                    w.configure(bg=t["bg"], fg=fg)
                elif cls == "Labelframe":
                    w.configure(bg=t["bg"], fg=t["fg"])
                elif cls == "Button":
                    self._theme_button(w, role)
                elif cls == "Text":
                    w.configure(bg=t["surface"], fg=t["fg"],
                                insertbackground=t["fg"],
                                selectbackground=t["accent"],
                                selectforeground="#ffffff")
                elif cls == "Listbox":
                    w.configure(bg=t["surface"], fg=t["fg"],
                                selectbackground=t["accent"],
                                selectforeground="#ffffff")
                elif cls == "Entry":
                    w.configure(bg=t["entry_bg"], fg=t["fg"],
                                insertbackground=t["fg"],
                                readonlybackground=t["entry_bg"])
                elif cls == "Checkbutton":
                    w.configure(bg=t["bg"], fg=t["fg"],
                                activebackground=t["bg"],
                                activeforeground=t["fg"],
                                selectcolor=t["surface"])
                elif cls == "Scrollbar":
                    w.configure(bg=t["plain_btn"], troughcolor=t["bg"],
                                activebackground=t["muted"])
            except tk.TclError:
                pass
            self._walk(w)
        # Status bar is pinned with side="bottom"; handle via role too.
        status = getattr(self, "status", None)
        if status is not None:
            status.configure(bg=t["statusbar"], fg=t["fg"])

    def _theme_button(self, w: tk.Button, role: str | None) -> None:
        t = self.t
        palette = {
            "accent": (t["accent"], t["accent_hover"], "#ffffff"),
            "danger": (t["danger"], t["danger_hover"], "#ffffff"),
            "purple": (t["purple"], t["purple_hover"], "#ffffff"),
            "green": (t["green"], t["green_hover"], "#ffffff"),
            "gray": (t["gray_btn"], t["gray_btn_hover"], "#ffffff"),
            "plain": (t["plain_btn"], t["gray_btn"], t["fg"]),
        }
        bg, hover, fg = palette.get(role or "plain", palette["plain"])
        w.configure(bg=bg, fg=fg, activebackground=hover,
                    activeforeground=fg)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        t = self.t
        pad = {"padx": 16, "pady": 6}

        header = tk.Frame(self.root, bg=t["bg"])
        header.pack(fill="x", **pad)

        title_row = tk.Frame(header, bg=t["bg"])
        title_row.pack(fill="x")
        tk.Label(title_row, text="Redaction Tool", font=("Segoe UI", 18, "bold"),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.theme_btn = tk.Button(title_row, text="🌙 Dark mode",
                                   command=self.toggle_theme,
                                   font=("Segoe UI", 9), padx=10, pady=2,
                                   relief="flat", cursor="hand2")
        self.theme_btn._theme_role = "plain"
        self.theme_btn.pack(side="right")

        subtitle = tk.Label(header,
                            text="Permanently redact FERPA/HIPAA-protected information from PDF, DOCX and XLSX files.",
                            font=("Segoe UI", 10), bg=t["bg"], fg=t["muted"])
        subtitle._theme_role = "muted"
        subtitle.pack(anchor="w")

        # ── 1. Files ──────────────────────────────────────────────────────
        files_frame = tk.LabelFrame(self.root, text=" 1. Choose documents  ",
                                    font=("Segoe UI", 10, "bold"), bg=t["bg"],
                                    fg=t["fg"], padx=12, pady=10)
        files_frame.pack(fill="both", expand=True, **pad)

        btn_row = tk.Frame(files_frame, bg=t["bg"])
        btn_row.pack(fill="x")
        self._button(btn_row, "Add Files…", self.add_files, "accent").pack(side="left")
        self._button(btn_row, "Remove Selected", self.remove_selected, "gray").pack(
            side="left", padx=8)
        self._button(btn_row, "Clear All", self.clear_files, "gray").pack(side="left")
        hint_text = "or drag & drop files here" if _DND_OK else "(drag & drop unavailable)"
        hint = tk.Label(btn_row, text=hint_text, font=("Segoe UI", 9, "italic"),
                        bg=t["bg"], fg=t["faint"])
        hint._theme_role = "faint"
        hint.pack(side="left", padx=12)

        list_wrap = tk.Frame(files_frame, bg=t["bg"])
        list_wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.file_list = tk.Listbox(list_wrap, font=("Consolas", 9), height=6,
                                    selectmode="extended", activestyle="none",
                                    relief="flat")
        scroll = tk.Scrollbar(list_wrap, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # ── 2. Redaction profile ──────────────────────────────────────────
        profile_frame = tk.LabelFrame(self.root, text=" 2. Redaction profile  ",
                                      font=("Segoe UI", 10, "bold"), bg=t["bg"],
                                      fg=t["fg"], padx=12, pady=10)
        profile_frame.pack(fill="x", **pad)

        preset_row = tk.Frame(profile_frame, bg=t["bg"])
        preset_row.pack(fill="x")
        tk.Label(preset_row, text="Preset:", font=("Segoe UI", 10),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(preset_row, textvariable=self.preset_var,
                                         state="readonly", width=32)
        self.preset_combo.pack(side="left", padx=8)
        self._button(preset_row, "Customize / Save Preset…", self.open_customizer,
                     "purple", font_size=9).pack(side="left", padx=4)
        self._button(preset_row, "Delete Custom Preset", self.delete_preset,
                     "gray", font_size=9).pack(side="left", padx=4)
        self._reload_presets()

        lbl1 = tk.Label(profile_frame,
                        text="Extra literal texts to redact — one per line (recommended: full names of case subjects):",
                        font=("Segoe UI", 9), bg=t["bg"], fg=t["fg"],
                        anchor="w", justify="left")
        lbl1.pack(fill="x", pady=(10, 2))
        self.custom_texts = tk.Text(profile_frame, height=3, font=("Consolas", 9),
                                    wrap="word", relief="flat")
        self.custom_texts.pack(fill="x")

        lbl2 = tk.Label(profile_frame,
                        text="Extra regex patterns — one per line (advanced):",
                        font=("Segoe UI", 9), bg=t["bg"], fg=t["fg"], anchor="w")
        lbl2.pack(fill="x", pady=(8, 2))
        self.custom_patterns = tk.Text(profile_frame, height=2, font=("Consolas", 9),
                                       wrap="word", relief="flat")
        self.custom_patterns.pack(fill="x")

        # ── 3. Output ─────────────────────────────────────────────────────
        out_frame = tk.LabelFrame(self.root, text=" 3. Output  ",
                                  font=("Segoe UI", 10, "bold"), bg=t["bg"],
                                  fg=t["fg"], padx=12, pady=10)
        out_frame.pack(fill="x", **pad)

        dir_row = tk.Frame(out_frame, bg=t["bg"])
        dir_row.pack(fill="x")
        tk.Label(dir_row, text="Output folder:", font=("Segoe UI", 10),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.out_dir_var = tk.StringVar(value="(same folder as source)")
        self.out_dir_entry = tk.Entry(dir_row, textvariable=self.out_dir_var,
                                      font=("Segoe UI", 9), width=52, relief="flat")
        self.out_dir_entry.pack(side="left", padx=8)
        self._button(dir_row, "Browse…", self.choose_out_dir, "plain",
                     font_size=9).pack(side="left")

        opt_row = tk.Frame(out_frame, bg=t["bg"])
        opt_row.pack(fill="x", pady=(8, 0))
        tk.Label(opt_row, text="Filename suffix:", font=("Segoe UI", 10),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.suffix_var = tk.StringVar(value="_REDACTED")
        tk.Entry(opt_row, textvariable=self.suffix_var, font=("Segoe UI", 9),
                 width=14, relief="flat").pack(side="left", padx=(8, 20))

        tk.Label(opt_row, text="Replacement text:", font=("Segoe UI", 10),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.replacement_var = tk.StringVar(value=redactor.DEFAULT_REPLACEMENT)
        tk.Entry(opt_row, textvariable=self.replacement_var, font=("Segoe UI", 9),
                 width=14, relief="flat").pack(side="left", padx=8)

        ocr_row = tk.Frame(out_frame, bg=t["bg"])
        ocr_row.pack(fill="x", pady=(8, 0))
        self.ocr_enabled_var = tk.BooleanVar(value=False)
        tesseract_found = ocr.find_tesseract() is not None
        ocr_text = "Enable OCR (scanned/image-only documents)"
        if not tesseract_found:
            ocr_text += " — Tesseract not found"
        self.ocr_cb = tk.Checkbutton(ocr_row, text=ocr_text,
                                      variable=self.ocr_enabled_var,
                                      font=("Segoe UI", 10),
                                      bg=t["bg"], fg=t["fg"],
                                      activebackground=t["bg"],
                                      activeforeground=t["fg"],
                                      selectcolor=t["surface"])
        self.ocr_cb.pack(side="left")
        if not tesseract_found:
            self.ocr_cb.configure(state="disabled")
        self.presidio_var = tk.BooleanVar(value=False)
        self.presidio_cb = tk.Checkbutton(
            ocr_row, text="Presidio NER (if installed)",
            variable=self.presidio_var, font=("Segoe UI", 9),
            bg=t["bg"], fg=t["muted"], activebackground=t["bg"],
            activeforeground=t["fg"], selectcolor=t["surface"])
        self.presidio_cb._theme_role = "muted"
        self.presidio_cb.pack(side="left", padx=(12, 0))

        img_row = tk.Frame(out_frame, bg=t["bg"])
        img_row.pack(fill="x", pady=(4, 0))
        self.image_var = tk.BooleanVar(value=False)
        tk.Checkbutton(img_row, text="Also render redacted PDFs as images",
                       variable=self.image_var, font=("Segoe UI", 10),
                       bg=t["bg"], fg=t["fg"], activebackground=t["bg"],
                       activeforeground=t["fg"], selectcolor=t["surface"]
                       ).pack(side="left")
        self.image_fmt_var = tk.StringVar(value="PNG")
        ttk.Combobox(img_row, textvariable=self.image_fmt_var, values=["PNG", "JPEG"],
                     state="readonly", width=6).pack(side="left", padx=8)

        # ── Actions ───────────────────────────────────────────────────────
        actions = tk.Frame(self.root, bg=t["bg"])
        actions.pack(fill="x", **pad)
        self.scan_btn = self._button(actions, "Scan (preview counts)", self.scan_files,
                                     "accent", font_size=11, bold=True)
        self.scan_btn.pack(side="left")
        self.redact_btn = self._button(actions, "Redact All", self.redact_all,
                                       "danger", font_size=11, bold=True)
        self.redact_btn.pack(side="left", padx=10)
        self.verify_btn = self._button(actions, "Verify Last Batch",
                                       self.verify_last_batch,
                                       "green", font_size=11, bold=True,
                                       state="disabled")
        self.verify_btn.pack(side="left")

        # Scan results
        results_wrap = tk.Frame(self.root, bg=t["bg"])
        results_wrap.pack(fill="both", expand=True, padx=16, pady=(0, 4))
        self.results = tk.Text(results_wrap, height=8, font=("Consolas", 9),
                               wrap="none", state="disabled", relief="flat")
        res_scroll = tk.Scrollbar(results_wrap, orient="vertical",
                                  command=self.results.yview)
        self.results.configure(yscrollcommand=res_scroll.set)
        self.results.pack(side="left", fill="both", expand=True)
        res_scroll.pack(side="right", fill="y")

        # Status bar
        self.status = tk.Label(self.root, text="Ready — add documents to begin.",
                               anchor="w", font=("Segoe UI", 9),
                               bg=t["statusbar"], fg=t["fg"], padx=12, pady=4)
        self.status.pack(fill="x", side="bottom")

    def _button(self, parent, text: str, command, role: str,
                font_size: int = 10, bold: bool = False,
                state: str = "normal") -> tk.Button:
        """Create a themed button; role ∈ accent|danger|purple|green|gray|plain."""
        t = self.t
        palette = {
            "accent": (t["accent"], t["accent_hover"], "#ffffff"),
            "danger": (t["danger"], t["danger_hover"], "#ffffff"),
            "purple": (t["purple"], t["purple_hover"], "#ffffff"),
            "green": (t["green"], t["green_hover"], "#ffffff"),
            "gray": (t["gray_btn"], t["gray_btn_hover"], "#ffffff"),
            "plain": (t["plain_btn"], t["gray_btn"], t["fg"]),
        }
        bg, hover, fg = palette[role]
        font = ("Segoe UI", font_size, "bold") if bold else ("Segoe UI", font_size)
        btn = tk.Button(parent, text=text, command=command, font=font,
                        bg=bg, fg=fg, activebackground=hover,
                        activeforeground=fg, padx=12, pady=3, relief="flat",
                        cursor="hand2", state=state,
                        disabledforeground=t["muted"])
        btn._theme_role = role
        return btn

    # --------------------------------------------------------------- files
    def _bind_dnd(self, root) -> None:
        if not _DND_OK:
            return
        try:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:  # noqa: BLE001 — degrade gracefully without DnD
            pass

    def _on_drop(self, event) -> None:
        raw = event.data
        # tkinterdnd2 supplies a space-separated list of {braced} paths.
        paths: list[str] = []
        while raw:
            raw = raw.strip()
            if raw.startswith("{"):
                end = raw.find("}")
                paths.append(raw[1:end])
                raw = raw[end + 1:]
            else:
                parts = raw.split(None, 1)
                paths.append(parts[0])
                raw = parts[1] if len(parts) > 1 else ""
        self._add_paths(paths)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Choose documents",
                                            filetypes=FILE_TYPES)
        self._add_paths(list(paths))

    def _add_paths(self, paths: list[str]) -> None:
        added = 0
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext not in redactor.SUPPORTED_EXTENSIONS:
                continue
            if p not in self.files:
                self.files.append(p)
                self.file_list.insert("end", p)
                added += 1
        if added:
            self.status.config(text=f"{len(self.files)} file(s) queued.")

    def remove_selected(self) -> None:
        for idx in reversed(self.file_list.curselection()):
            del self.files[idx]
            self.file_list.delete(idx)

    def clear_files(self) -> None:
        self.files.clear()
        self.file_list.delete(0, "end")

    # ------------------------------------------------------------- presets
    def _reload_presets(self) -> None:
        all_p = presets.list_all_presets()
        names = list(all_p)
        self.preset_combo.configure(values=names)
        if not self.preset_var.get() or self.preset_var.get() not in all_p:
            self.preset_var.set("Full (FERPA + HIPAA)" if
                                "Full (FERPA + HIPAA)" in all_p else names[0])

    def _current_categories(self) -> list[str]:
        all_p = presets.list_all_presets()
        return all_p.get(self.preset_var.get(), detector.PRESETS["Full (FERPA + HIPAA)"])

    def open_customizer(self) -> None:
        CustomizerDialog(self.root, current=self._current_categories(),
                         on_save=self._on_preset_saved, theme=self.t)

    def _on_preset_saved(self, name: str, categories: list[str]) -> None:
        presets.save_preset(name, categories)
        self._reload_presets()
        self.preset_var.set(name)

    def delete_preset(self) -> None:
        name = self.preset_var.get()
        if name in detector.PRESETS:
            messagebox.showinfo("Built-in preset",
                                "Built-in presets cannot be deleted.")
            return
        if presets.delete_preset(name):
            self._reload_presets()
            self.status.config(text=f"Deleted preset '{name}'.")
        else:
            messagebox.showinfo("Not found", f"No custom preset named '{name}'.")

    # ------------------------------------------------------------ options
    def choose_out_dir(self) -> None:
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.out_dir_var.set(d)

    def _out_dir(self) -> str | None:
        v = self.out_dir_var.get().strip()
        if not v or v.startswith("("):
            return None
        return v

    def _scan_options(self, salt: str = "") -> redactor.ScanOptions:
        texts = [ln.strip() for ln in self.custom_texts.get("1.0", "end").splitlines()
                 if ln.strip()]
        patterns = [ln.strip() for ln in
                    self.custom_patterns.get("1.0", "end").splitlines() if ln.strip()]
        return redactor.ScanOptions(
            enabled_categories=self._current_categories(),
            custom_patterns=patterns or None,
            custom_texts=texts or None,
            replacement=self.replacement_var.get() or redactor.DEFAULT_REPLACEMENT,
            hash_salt=salt,
            use_presidio=self.presidio_var.get(),
        )

    def _write_results(self, lines: list[str]) -> None:
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", "\n".join(lines))
        self.results.configure(state="disabled")

    # ------------------------------------------------------------- actions
    # ----------------------------------------------------- batch engine
    def _build_payload(self, salt: str) -> dict:
        """Gather all settings on the main thread before the worker starts."""
        return {
            "files": list(self.files),
            "opts": self._scan_options(salt=salt),
            "use_ocr": (self.ocr_enabled_var.get()
                        and ocr.find_tesseract() is not None),
            "out_dir": self._out_dir(),
            "suffix": self.suffix_var.get() or "_REDACTED",
            "preset": self.preset_var.get(),
            "image_output": self.image_var.get(),
            "image_format": self.image_fmt_var.get(),
        }

    def _start_batch(self, kind: str, payload: dict) -> None:
        self._batch_queue: queue.Queue = queue.Queue()
        self._set_batch_ui(running=True)
        worker = threading.Thread(
            target=self._batch_worker, args=(kind, payload, self._batch_queue),
            daemon=True)
        worker.start()
        self.root.after(100, self._poll_batch, kind)

    def _set_batch_ui(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        for btn in (self.scan_btn, self.redact_btn):
            btn.config(state=state)
        if running:
            self.verify_btn.config(state="disabled")

    def _poll_batch(self, kind: str) -> None:
        q = self._batch_queue
        done = None
        if q is not None:
            try:
                while True:
                    msg = q.get_nowait()
                    if msg[0] == "progress":
                        self.status.config(text=msg[1])
                    elif msg[0] == "done":
                        done = msg[1]
            except queue.Empty:
                pass
        if done is not None:
            self._batch_queue = None
            self._finish_batch(kind, done)
        else:
            self.root.after(100, self._poll_batch, kind)

    def _finish_batch(self, kind: str, done: dict) -> None:
        self._set_batch_ui(running=False)
        self._write_results(done["lines"])
        if kind == "redact":
            self.last_outputs = done.get("outputs", [])
            self.verify_btn.config(
                state="normal" if self.last_outputs else "disabled")
            msg = f"Redacted {done['ok']} of {done['total']} file(s)."
            if done["failed"]:
                msg += f"\n{done['failed']} file(s) failed — see list above."
            if done.get("log_path"):
                msg += f"\nAudit log: {done['log_path']}"
            self.status.config(text=msg.replace("\n", " "))
            messagebox.showinfo("Redaction complete", msg)
        elif kind == "verify":
            msg = (f"Verification: {done['pass_count']} PASS, "
                   f"{done['review_count']} NEEDS_REVIEW "
                   f"(of {done['total']} file(s)).\n"
                   "See the results list for details.")
            self.status.config(text=msg.replace("\n", " "))
            messagebox.showinfo("Verification complete", msg)

    # Verify a single redacted output.  For PDFs with OCR enabled the OCR
    # pass covers both the text layer and raster content; otherwise the
    # text-based detector re-scans the output.
    def _verify_one(self, path: Path, opts, use_ocr: bool) -> dict:
        ext = path.suffix.lower()
        try:
            if ext in ocr.IMAGE_EXTS or (ext == ".pdf" and use_ocr):
                v = ocr.verify_ocr(path, scan_opts=opts)
                return {"status": v["status"],
                        "residual": v["remaining_detection_count"],
                        "warnings": v["warnings"]}
            counts = redactor.scan_file(path, opts)
            n = sum(counts.values())
            return {"status": "PASS" if n == 0 else "NEEDS_REVIEW",
                    "residual": n, "warnings": []}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "residual": None, "warnings": [str(exc)]}

    # ------------------------------------------------------------- actions
    def scan_files(self) -> None:
        if not self.files:
            messagebox.showinfo("No files", "Add at least one document first.")
            return
        salt = secrets.token_hex(16)
        self._start_batch("scan", self._build_payload(salt))

    def redact_all(self) -> None:
        if not self.files:
            messagebox.showinfo("No files", "Add at least one document first.")
            return
        if not messagebox.askyesno(
            "Confirm redaction",
            f"Redact {len(self.files)} file(s) with preset "
            f"'{self.preset_var.get()}'?\n\n"
            "Redacted copies will be written with the configured suffix; "
            "originals are never modified."):
            return
        salt = secrets.token_hex(16)
        self._start_batch("redact", self._build_payload(salt))

    def verify_last_batch(self) -> None:
        if not self.last_outputs:
            messagebox.showinfo("Nothing to verify",
                                "Redact a batch first, then verify.")
            return
        payload = self._build_payload(salt=secrets.token_hex(16))
        payload["outputs"] = list(self.last_outputs)
        self._start_batch("verify", payload)

    # --------------------------------------------------- batch workers
    # These run on a background thread — no tkinter calls here.  Progress
    # and the final result go through the queue.
    def _batch_worker(self, kind: str, payload: dict, q: queue.Queue) -> None:
        try:
            if kind == "scan":
                q.put(("done", self._scan_worker(payload, q)))
            elif kind == "verify":
                q.put(("done", self._verify_worker(payload, q)))
            else:
                q.put(("done", self._redact_worker(payload, q)))
        except Exception as exc:  # noqa: BLE001 — never hang the UI
            q.put(("done", {"lines": [f"BATCH ERROR: {exc}"], "ok": 0,
                            "failed": 0, "total": 0, "outputs": []}))

    def _scan_worker(self, payload: dict, q: queue.Queue) -> dict:
        opts = payload["opts"]
        use_ocr = payload["use_ocr"]
        files = payload["files"]
        lines: list[str] = []
        total_all = 0
        for i, path_str in enumerate(files, 1):
            path = Path(path_str)
            name = path.name
            q.put(("progress", f"Scanning {i}/{len(files)}: {name}…"))
            counts: dict[str, int] = {}
            ext = path.suffix.lower()

            if ext in ocr.IMAGE_EXTS:
                if not use_ocr:
                    lines.append(f"{name}:  Image file — enable OCR to scan")
                    continue
                try:
                    plan = ocr.scan_ocr_image(path, scan_opts=opts)
                    for d in plan["detections"]:
                        counts[d["entity_type"]] = counts.get(d["entity_type"], 0) + 1
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{name}:  OCR ERROR — {exc}")
                    continue
            else:
                try:
                    text_counts = redactor.scan_file(path, opts)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{name}:  ERROR — {exc}")
                    continue
                for cat, n in text_counts.items():
                    counts[cat] = counts.get(cat, 0) + n
                if ext == ".pdf" and use_ocr:
                    if sum(text_counts.values()) == 0:
                        lines.append("  (text layer is empty — running OCR)")
                    try:
                        plan = ocr.scan_ocr_pdf(path, scan_opts=opts)
                        for d in plan["detections"]:
                            counts[d["entity_type"]] = counts.get(d["entity_type"], 0) + 1
                    except Exception as exc:  # noqa: BLE001
                        lines.append(f"  OCR ERROR — {exc}")

            total = sum(counts.values())
            total_all += total
            lines.append(f"{name}:  {total} item(s) detected")
            for cat, n in sorted(counts.items()):
                label = detector.CATEGORY_MAP.get(cat)
                lines.append(f"    {label.label if label else cat}: {n}")
        lines.append("")
        lines.append(f"TOTAL: {total_all} item(s) across {len(files)} file(s)")
        return {"lines": lines}

    def _verify_worker(self, payload: dict, q: queue.Queue) -> dict:
        opts = payload["opts"]
        use_ocr = payload["use_ocr"]
        outputs = payload["outputs"]
        lines: list[str] = []
        pass_count = review_count = 0
        for i, path in enumerate(outputs, 1):
            q.put(("progress", f"Verifying {i}/{len(outputs)}: {path.name}…"))
            v = self._verify_one(path, opts, use_ocr)
            if v["status"] == "PASS":
                pass_count += 1
            elif v["status"] in ("NEEDS_REVIEW", "ERROR"):
                review_count += 1
            lines.append(f"{path.name}:  VERIFY {v['status']} "
                         f"(residual={v['residual']})")
            for w in v["warnings"]:
                lines.append(f"    warning: {w}")
        lines.append("")
        lines.append(f"RESULT: {pass_count} PASS, {review_count} NEEDS_REVIEW")
        return {"lines": lines, "pass_count": pass_count,
                "review_count": review_count, "total": len(outputs)}

    def _redact_worker(self, payload: dict, q: queue.Queue) -> dict:
        opts = payload["opts"]
        use_ocr = payload["use_ocr"]
        files = payload["files"]
        out_dir = payload["out_dir"]
        suffix = payload["suffix"]
        preset = payload["preset"]
        lines: list[str] = []
        outputs: list[Path] = []
        log_entries: list[dict] = []
        ok = failed = 0

        for i, path_str in enumerate(files, 1):
            path = Path(path_str)
            name = path.name
            q.put(("progress", f"Redacting {i}/{len(files)}: {name}…"))
            entry: dict = {
                "source": str(path),
                "preset": preset,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "hash_salt": opts.hash_salt,
                "ocr_used": False,
                "errors": [],
            }
            ext = path.suffix.lower()

            if ext in ocr.IMAGE_EXTS:
                if not use_ocr:
                    failed += 1
                    entry["errors"].append("OCR must be enabled for image files")
                    lines.append(f"{name}:  ERROR — OCR must be enabled for images")
                    log_entries.append(entry)
                    continue
                out_path = (Path(out_dir) / f"{path.stem}{suffix}{ext}"
                            if out_dir
                            else path.with_name(f"{path.stem}{suffix}{ext}"))
                try:
                    plan = ocr.scan_ocr_image(path, scan_opts=opts)
                    ocr.apply_ocr_redactions(path, plan, out_path)
                    ok += 1
                    entry["outputs"] = [str(out_path)]
                    entry["ocr_used"] = True
                    entry["plan"] = {"detections": len(plan["detections"]),
                                     "warnings": plan["warnings"]}
                    lines.append(f"{name}:  {len(plan['detections'])} OCR redaction(s) applied")
                    lines.append(f"    → {out_path}")
                    outputs.append(out_path)
                    # Persist the full redaction plan (audit artifact).
                    try:
                        plan_path = out_path.with_suffix(out_path.suffix + ".plan.json")
                        plan_path.write_text(json.dumps(plan, indent=2),
                                             encoding="utf-8")
                        entry["plan_file"] = str(plan_path)
                    except Exception:
                        pass
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    entry["errors"].append(str(exc))
                    lines.append(f"{name}:  OCR ERROR — {exc}")
                log_entries.append(entry)
                continue

            # Text-based documents — standard redaction first.
            result = redactor.redact_file(
                path, opts, out_dir=out_dir, suffix=suffix,
                image_output=payload["image_output"],
                image_format=payload["image_format"],
            )
            if result.error:
                failed += 1
                entry["errors"].append(result.error)
                lines.append(f"{name}:  ERROR — {result.error}")
                log_entries.append(entry)
                continue

            entry["outputs"] = [str(o) for o in result.outputs]
            entry["redaction_count"] = result.redaction_count
            entry["per_category"] = result.per_category
            if result.recoverability:
                entry["recoverability"] = result.recoverability
                entry["recoverability_leaked"] = result.recoverability_leaked
                if result.recoverability != "PASS":
                    lines.append(f"    RECOVERABILITY: {result.recoverability} "
                                 f"(leaked={result.recoverability_leaked})")

            # If OCR enabled, apply OCR redactions on top of the text pass.
            if use_ocr and ext == ".pdf":
                redacted_pdf = result.outputs[0]
                try:
                    ocr_plan = ocr.scan_ocr_pdf(redacted_pdf, scan_opts=opts)
                    if ocr_plan["detections"]:
                        temp = redacted_pdf.with_suffix(".ocr_tmp.pdf")
                        ocr.apply_ocr_redactions(redacted_pdf, ocr_plan, temp)
                        temp.replace(redacted_pdf)
                        entry["ocr_used"] = True
                        entry["ocr_overlay"] = len(ocr_plan["detections"])
                        lines.append(f"  + {len(ocr_plan['detections'])} OCR overlay redaction(s)")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"  OCR pass skipped — {exc}")

            ok += 1
            lines.append(f"{name}:  {result.redaction_count} redaction(s) applied")
            for out in result.outputs:
                lines.append(f"    → {out}")
                outputs.append(out)

            # Verify the primary output immediately.
            primary = result.outputs[0]
            q.put(("progress", f"Verifying {name}…"))
            v = self._verify_one(primary, opts, use_ocr)
            entry["verify"] = v
            lines.append(f"    VERIFY: {v['status']} (residual={v['residual']})")
            for w in v["warnings"]:
                lines.append(f"      warning: {w}")
            log_entries.append(entry)

        # Persist the batch audit log next to the outputs.
        log_path = None
        if log_entries:
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                base = Path(out_dir) if out_dir else Path(files[0]).parent
                log_path = base / f"redaction_log_{stamp}.json"
                log_path.write_text(json.dumps({
                    "tool_version": _tool_version(),
                    "preset": preset,
                    "hash_salt": opts.hash_salt,
                    "replacement": opts.replacement,
                    "entries": log_entries,
                }, indent=2), encoding="utf-8")
                lines.append("")
                lines.append(f"Audit log: {log_path}")
            except Exception:
                pass

        return {"lines": lines, "ok": ok, "failed": failed,
                "total": len(files), "outputs": outputs,
                "log_path": str(log_path) if log_path else None}


def _tool_version() -> str:
    from . import __version__
    return __version__

class CustomizerDialog:
    """Checkbox dialog for toggling categories and saving custom presets."""

    def __init__(self, parent: tk.Tk, current: list[str], on_save,
                 theme: dict[str, str]) -> None:
        self.on_save = on_save
        t = theme
        self.win = tk.Toplevel(parent)
        self.win.title("Customize Redaction Categories")
        self.win.configure(bg=t["bg"])
        self.win.transient(parent)
        self.win.grab_set()

        tk.Label(self.win, text="Select the categories to redact:",
                 font=("Segoe UI", 10, "bold"), bg=t["bg"],
                 fg=t["fg"]).pack(anchor="w", padx=16, pady=(14, 6))

        body = tk.Frame(self.win, bg=t["bg"])
        body.pack(fill="both", expand=True, padx=16)

        self.vars: dict[str, tk.BooleanVar] = {}
        for cat in detector.CATEGORIES:
            var = tk.BooleanVar(value=cat.key in current)
            self.vars[cat.key] = var
            tk.Checkbutton(body, text=cat.label, variable=var,
                           font=("Segoe UI", 9), bg=t["bg"], fg=t["fg"],
                           activebackground=t["bg"], activeforeground=t["fg"],
                           selectcolor=t["surface"], anchor="w",
                           justify="left", wraplength=560).pack(fill="x")

        tk.Label(self.win,
                 text="Note: HIPAA identifier #17 (full-face photos) cannot be "
                      "auto-detected — review PDFs manually.",
                 font=("Segoe UI", 8, "italic"), bg=t["bg"], fg=t["muted"],
                 wraplength=560, justify="left").pack(padx=16, pady=(6, 0))

        row = tk.Frame(self.win, bg=t["bg"])
        row.pack(fill="x", padx=16, pady=14)
        tk.Label(row, text="Save as preset:", font=("Segoe UI", 10),
                 bg=t["bg"], fg=t["fg"]).pack(side="left")
        self.name_entry = tk.Entry(row, font=("Segoe UI", 9), width=24,
                                   bg=t["entry_bg"], fg=t["fg"],
                                   insertbackground=t["fg"], relief="flat")
        self.name_entry.pack(side="left", padx=8)
        tk.Button(row, text="Save & Use", command=self._save,
                  font=("Segoe UI", 9, "bold"), bg=t["green"], fg="#ffffff",
                  activebackground=t["green_hover"], activeforeground="#ffffff",
                  padx=10, pady=2, relief="flat", cursor="hand2").pack(side="left")
        tk.Button(row, text="Close", command=self.win.destroy,
                  font=("Segoe UI", 9), padx=10, pady=2, relief="flat",
                  bg=t["plain_btn"], fg=t["fg"], cursor="hand2").pack(
            side="left", padx=8)

    def _save(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showinfo("Name required", "Enter a name for the preset.",
                                parent=self.win)
            return
        categories = [k for k, v in self.vars.items() if v.get()]
        if not categories:
            messagebox.showinfo("No categories", "Select at least one category.",
                                parent=self.win)
            return
        self.on_save(name, categories)
        self.win.destroy()


def main() -> None:
    root = TkinterDnD.Tk() if _DND_OK else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
