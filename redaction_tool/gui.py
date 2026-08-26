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
        self._button(actions, "Scan (preview counts)", self.scan_files,
                     "accent", font_size=11, bold=True).pack(side="left")
        self._button(actions, "Redact All", self.redact_all,
                     "danger", font_size=11, bold=True).pack(side="left", padx=10)

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
                font_size: int = 10, bold: bool = False) -> tk.Button:
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
                        cursor="hand2")
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

    def _scan_options(self) -> redactor.ScanOptions:
        texts = [ln.strip() for ln in self.custom_texts.get("1.0", "end").splitlines()
                 if ln.strip()]
        patterns = [ln.strip() for ln in
                    self.custom_patterns.get("1.0", "end").splitlines() if ln.strip()]
        return redactor.ScanOptions(
            enabled_categories=self._current_categories(),
            custom_patterns=patterns or None,
            custom_texts=texts or None,
            replacement=self.replacement_var.get() or redactor.DEFAULT_REPLACEMENT,
        )

    def _write_results(self, lines: list[str]) -> None:
        self.results.configure(state="normal")
        self.results.delete("1.0", "end")
        self.results.insert("1.0", "\n".join(lines))
        self.results.configure(state="disabled")

    # ------------------------------------------------------------- actions
    def scan_files(self) -> None:
        if not self.files:
            messagebox.showinfo("No files", "Add at least one document first.")
            return
        opts = self._scan_options()
        use_ocr = (self.ocr_enabled_var.get()
                   and ocr.find_tesseract() is not None)
        lines: list[str] = []
        total_all = 0
        for i, path_str in enumerate(self.files, 1):
            path = Path(path_str)
            name = path.name
            self.status.config(text=f"Scanning {i}/{len(self.files)}: {name}…")
            self.root.update_idletasks()

            counts: dict[str, int] = {}
            ext = path.suffix.lower()

            # Image-only files always use OCR
            if ext in ocr.IMAGE_EXTS:
                if use_ocr:
                    try:
                        plan = ocr.scan_ocr_image(path, scan_opts=opts)
                        for d in plan["detections"]:
                            cat = d["entity_type"]
                            counts[cat] = counts.get(cat, 0) + 1
                    except Exception as exc:  # noqa: BLE001
                        lines.append(f"{name}:  OCR ERROR — {exc}")
                        continue
                else:
                    lines.append(f"{name}:  Image file — enable OCR to scan")
                    continue
            else:
                # Text-based: run normal scan + optional OCR
                try:
                    text_counts = redactor.scan_file(path, opts)
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"{name}:  ERROR — {exc}")
                    continue
                # Merge text results
                for cat, n in text_counts.items():
                    counts[cat] = counts.get(cat, 0) + n

                # If PDF is image-only (0 text) and OCR enabled, add OCR
                if ext == ".pdf" and use_ocr:
                    if sum(text_counts.values()) == 0:
                        lines.append(f"  (text layer is empty — running OCR)")
                    try:
                        plan = ocr.scan_ocr_pdf(path, scan_opts=opts)
                        for d in plan["detections"]:
                            cat = d["entity_type"]
                            counts[cat] = counts.get(cat, 0) + 1
                    except Exception as exc:  # noqa: BLE001
                        lines.append(f"  OCR ERROR — {exc}")

            total = sum(counts.values())
            total_all += total
            lines.append(f"{name}:  {total} item(s) detected")
            for cat, n in sorted(counts.items()):
                label = detector.CATEGORY_MAP.get(cat)
                lines.append(f"    {label.label if label else cat}: {n}")
        lines.append("")
        lines.append(f"TOTAL: {total_all} item(s) across {len(self.files)} file(s)")
        self._write_results(lines)
        self.status.config(text="Scan complete. Review counts, then Redact All.")

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

        opts = self._scan_options()
        out_dir = self._out_dir()
        suffix = self.suffix_var.get() or "_REDACTED"
        use_ocr = (self.ocr_enabled_var.get()
                   and ocr.find_tesseract() is not None)
        lines: list[str] = []
        ok, failed = 0, 0

        for i, path_str in enumerate(self.files, 1):
            path = Path(path_str)
            name = path.name
            self.status.config(text=f"Redacting {i}/{len(self.files)}: {name}…")
            self.root.update_idletasks()
            ext = path.suffix.lower()

            if ext in ocr.IMAGE_EXTS:
                # Image-only: use OCR redaction exclusively
                if not use_ocr:
                    failed += 1
                    lines.append(f"{name}:  ERROR — OCR must be enabled for images")
                    continue
                out_path = (Path(out_dir) / f"{path.stem}{suffix}{ext}"
                            if out_dir else path.with_name(f"{path.stem}{suffix}{ext}"))
                try:
                    plan = ocr.scan_ocr_image(path, scan_opts=opts)
                    ocr.apply_ocr_redactions(path, plan, out_path)
                    ok += 1
                    lines.append(f"{name}:  {len(plan['detections'])} OCR redaction(s) applied")
                    lines.append(f"    → {out_path}")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    lines.append(f"{name}:  OCR ERROR — {exc}")
                continue

            # Text-based documents — run standard redaction first
            result = redactor.redact_file(
                path, opts, out_dir=out_dir, suffix=suffix,
                image_output=self.image_var.get(),
                image_format=self.image_fmt_var.get(),
            )
            if result.error:
                failed += 1
                lines.append(f"{name}:  ERROR — {result.error}")
                continue

            # If OCR enabled, also apply OCR redactions on top
            if use_ocr and ext == ".pdf":
                redacted_pdf = result.outputs[0]
                try:
                    ocr_plan = ocr.scan_ocr_pdf(redacted_pdf, scan_opts=opts)
                    if ocr_plan["detections"]:
                        # Build a plan for the original, then apply to
                        # the redacted output (in-place overlay)
                        temp = redacted_pdf.with_suffix(".ocr_tmp.pdf")
                        ocr.apply_ocr_redactions(redacted_pdf, ocr_plan, temp)
                        temp.replace(redacted_pdf)
                        lines.append(f"  + {len(ocr_plan['detections'])} OCR overlay redaction(s)")
                except Exception as exc:  # noqa: BLE001
                    lines.append(f"  OCR pass skipped — {exc}")

            ok += 1
            lines.append(f"{name}:  {result.redaction_count} redaction(s) applied")
            for out in result.outputs:
                lines.append(f"    → {out}")

        self._write_results(lines)
        msg = f"Redacted {ok} of {len(self.files)} file(s)."
        if failed:
            msg += f"\n{failed} file(s) failed — see list above."
        self.status.config(text=msg.replace("\n", " "))
        messagebox.showinfo("Redaction complete", msg)


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
