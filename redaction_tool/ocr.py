"""OCR-aware redaction for scanned/image-only PDFs and standalone images.

No network calls — uses a local Tesseract executable for OCR and PyMuPDF
for true PDF redaction.  Integrates with the full detector.py pipeline so
that the same 19 FERPA/HIPAA categories are applied to OCR-extracted text.

Workflow:  scan → generate redaction plan (JSON with bounding boxes) →
review/edit plan → apply (permanent redaction) → verify (re-scan output).

Based on ocr-redaction-local v1.0.0 methodology (see references/methodology.md).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import detector

# ── Dependencies ───────────────────────────────────────────────────────────

def _require_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
            return pymupdf
        except ImportError:
            raise RuntimeError("PyMuPDF is required for PDF OCR redaction.")

try:
    from PIL import Image, ImageDraw  # noqa: F401 — used by apply_image
    _PILLOW_OK = True
except ImportError:
    _PILLOW_OK = False

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
PDF_EXTS = {".pdf"}

DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ── Tesseract ──────────────────────────────────────────────────────────────

@dataclass
class OCRWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float
    start: int = 0
    end: int = 0


def find_tesseract() -> Optional[str]:
    """Return the path to a working Tesseract executable, or None."""
    import shutil
    candidates = [
        os.environ.get("TESSERACT_CMD", ""),
        DEFAULT_TESSERACT,
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        shutil.which("tesseract") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
        if c:
            try:
                subprocess.run([c, "--version"], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5)
                return c
            except Exception:
                continue
    return None


def check_dependencies() -> dict:
    """Return a status dict of what's available for OCR workflows."""
    return {
        "tesseract": bool(find_tesseract()),
        "pymupdf": True,   # already required by the main tool
        "pillow": _PILLOW_OK,
    }


def run_ocr(image_path: Path, lang: str = "eng",
            tesseract_cmd: Optional[str] = None) -> list[OCRWord]:
    """Run Tesseract TSV OCR on a rendered page image.

    Returns OCRWord objects with pixel-coordinate bounding boxes and
    cumulative character offsets in a single-space word stream.
    """
    cmd = tesseract_cmd or find_tesseract()
    if not cmd:
        raise RuntimeError(
            "Tesseract OCR not found. Install from "
            "https://github.com/UB-Mannheim/tesseract/wiki and ensure "
            "tesseract.exe is on your PATH or set TESSERACT_CMD."
        )
    proc = subprocess.run(
        [cmd, str(image_path), "stdout", "-l", lang, "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"Tesseract failed: {proc.stderr.strip()}")

    rows = csv.DictReader(io.StringIO(proc.stdout), delimiter="\t")
    words: list[OCRWord] = []
    for r in rows:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        try:
            conf = float(r.get("conf") or -1)
            words.append(OCRWord(
                text, int(r["left"]), int(r["top"]),
                int(r["width"]), int(r["height"]), conf,
            ))
        except (ValueError, KeyError):
            continue

    # Assign cumulative character offsets for span-to-bbox mapping.
    pos = 0
    for i, w in enumerate(words):
        if i:
            pos += 1  # single space between words in the canonical stream
        w.start = pos
        pos += len(w.text)
        w.end = pos
    return words


def ocr_text(words: list[OCRWord]) -> str:
    """Reconstruct the single-space canonical text stream."""
    return " ".join(w.text for w in words)


# ── Bounding-box mapping ───────────────────────────────────────────────────

def span_bbox(words: list[OCRWord], start: int, end: int,
              ) -> Optional[tuple[int, int, int, int, float]]:
    """Map a character span [start, end) to a pixel bounding box.

    Returns (left, top, right, bottom, avg_ocr_confidence) or None.
    """
    hit = [w for w in words if w.end > start and w.start < end]
    if not hit:
        return None
    left = min(w.left for w in hit)
    top = min(w.top for w in hit)
    right = max(w.left + w.width for w in hit)
    bottom = max(w.top + w.height for w in hit)
    confs = [w.conf for w in hit if w.conf >= 0]
    avg_conf = sum(confs) / len(confs) if confs else -1.0
    return left, top, right, bottom, avg_conf


# ── Detection (integrated with our full detector) ──────────────────────────

# Optional Presidio entity types → our category keys.
_PRESIDIO_CATEGORY_MAP = {
    "PERSON": "names",
    "LOCATION": "addresses",
    "ORGANIZATION": "names",
    "EMAIL_ADDRESS": "emails",
    "PHONE_NUMBER": "phones",
    "US_SSN": "ssn",
    "IP_ADDRESS": "ips",
    "URL": "urls",
    "DATE_TIME": "dates",
}


def _presidio_spans(text: str) -> tuple[list[tuple[int, int, str, str, float]], list[str]]:
    """Run optional local Presidio NER.  Returns (spans, warnings).

    Never imports or starts any server — presidio-analyzer runs in-process.
    """
    warnings: list[str] = []
    try:
        from presidio_analyzer import AnalyzerEngine
    except ImportError:
        return [], ["Presidio requested but presidio-analyzer is not installed "
                    "— NER skipped."]
    try:
        analyzer = getattr(_presidio_spans, "_engine", None)
        if analyzer is None:
            analyzer = AnalyzerEngine()
            _presidio_spans._engine = analyzer  # cache across pages
        spans: list[tuple[int, int, str, str, float]] = []
        for res in analyzer.analyze(text=text, language="en"):
            spans.append((res.start, res.end, res.entity_type,
                          text[res.start:res.end], float(res.score)))
        return spans, warnings
    except Exception as exc:  # noqa: BLE001
        return [], [f"Presidio analysis failed: {exc}"]


def detect_on_ocr(words: list[OCRWord],
                  scan_opts: Optional["redactor_ScanOptions"] = None,
                  ) -> tuple[list[dict], list[str]]:
    """Run our 19-category detector against OCR-extracted text.

    Each match is converted to a redaction-plan entry with pixel-coordinate
    bounding boxes, masked previews (never full sensitive values), and
    salted SHA-256 fingerprints (unsalted hashes of short values such as
    SSNs are brute-forceable).

    Returns (plan_entries, warnings).
    """
    from .redactor import ScanOptions  # late import to avoid circular
    opts = scan_opts or ScanOptions()
    text = ocr_text(words)
    matches = opts.run_detection(text)  # uses our full detector.py
    warnings: list[str] = []

    # Optional local Presidio NER (covers names the built-in list misses).
    if getattr(opts, "use_presidio", False):
        spans, pres_warnings = _presidio_spans(text)
        warnings.extend(pres_warnings)
        for start, end, entity_type, value, score in spans:
            matches.append(detector.Match(
                text=value,
                category=_PRESIDIO_CATEGORY_MAP.get(entity_type, "custom"),
                start=start,
                end=end,
            ))
        # Re-deduplicate after merging.
        matches = _dedupe_matches(matches)

    salt = getattr(opts, "hash_salt", "") or ""

    plan_entries: list[dict] = []
    seen_spans: set[tuple[int, int]] = set()
    idx = 0
    for m in matches:
        if (m.start, m.end) in seen_spans:
            continue
        seen_spans.add((m.start, m.end))
        bb = span_bbox(words, m.start, m.end)
        if not bb:
            continue
        idx += 1
        left, top, right, bottom, conf = bb
        entry = {
            "id": f"ocr-{idx:05d}",
            "page": 1,  # will be overridden by caller for multi-page PDFs
            "entity_type": m.category,
            "source": "ocr+detector",
            "bbox": [round(float(x), 3) for x in (left, top, right, bottom)],
            "coordinate_space": "image_pixels",  # converted to pdf_points by caller
            "ocr_confidence": round(float(conf), 2) if conf >= 0 else None,
            "detector_confidence": 1.0,
            "preview": _mask_value(m.category, m.text),
            "sha256": hashlib.sha256((salt + m.text).encode("utf-8")).hexdigest(),
            "action": "redact",
        }
        plan_entries.append(entry)
    return plan_entries, warnings


def _dedupe_matches(matches: list):
    """Keep the longest match when ranges overlap."""
    matches.sort(key=lambda x: (x.start, -(x.end - x.start)))
    deduped: list = []
    for m in matches:
        if deduped and m.start < deduped[-1].end:
            if (m.end - m.start) > (deduped[-1].end - deduped[-1].start):
                deduped[-1] = m
            continue
        deduped.append(m)
    deduped.sort(key=lambda x: x.start)
    return deduped


def _mask_value(category: str, value: str) -> str:
    """Produce a safe preview — never stores the full sensitive value."""
    if category == "emails" and "@" in value:
        a, b = value.split("@", 1)
        return (a[:1] + "***@" + b) if a else "***@" + b
    digits = re.sub(r"\D", "", value)
    if category in ("ssn", "phones", "fax", "unique_ids") and len(digits) >= 4:
        return "***" + digits[-4:]
    if category == "ips":
        parts = value.split(".")
        return (".".join(parts[:1] + ["***", "***", parts[-1]])
                if len(parts) == 4 else "[REDACTED_IP]")
    if category == "urls":
        return "[REDACTED_URL]"
    if category == "names":
        # Mask to first initial
        parts = value.split()
        if len(parts) >= 2:
            return parts[0][:1] + "*** " + parts[-1][:1] + "***"
        return value[:1] + "***"
    return "[REDACTED]"


# ── Plan helpers ───────────────────────────────────────────────────────────

def new_plan(source_name: str, source_type: str, dpi: int = 200,
             lang: str = "eng") -> dict:
    return {
        "schema_version": 1,
        "source": {"name": source_name, "type": source_type},
        "settings": {"dpi": dpi, "ocr_language": lang},
        "detections": [],
        "warnings": [],
    }


# ── Image redaction ────────────────────────────────────────────────────────

def apply_image_redactions(src: Path, plan: dict, out: Path) -> None:
    """Draw opaque black rectangles over every redaction bbox in the plan."""
    if not _PILLOW_OK:
        raise RuntimeError("Pillow is required for image redaction.")
    img = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(img)
    for d in plan.get("detections", []):
        if d.get("action") != "redact" or d.get("coordinate_space") != "image_pixels":
            continue
        draw.rectangle(d["bbox"], fill="black")
    img.save(out)


def apply_pdf_ocr_redactions(pdf_path: Path, plan: dict, out: Path) -> None:
    """Apply ocr-derived redaction annotations + true apply_redactions()."""
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(pdf_path))
    by_page: dict[int, list[dict]] = {}
    for d in plan.get("detections", []):
        if d.get("action") != "redact" or d.get("coordinate_space") != "pdf_points":
            continue
        by_page.setdefault(int(d["page"]), []).append(d)
    for pno, entries in by_page.items():
        if pno < 1 or pno > len(doc):
            raise RuntimeError(f"Plan page {pno} out of range (1-{len(doc)}).")
        page = doc[pno - 1]
        for d in entries:
            rect = pymupdf.Rect(*d["bbox"])
            page.add_redact_annot(rect, fill=(0, 0, 0), cross_out=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
    doc.save(str(out), garbage=4, deflate=True)
    doc.close()


# ═══════════════════════════════════════════════════════════════════════════
# High-level scan / apply / verify
# ═══════════════════════════════════════════════════════════════════════════

def scan_ocr_pdf(pdf_path: Path, dpi: int = 200, lang: str = "eng",
                 tesseract_cmd: Optional[str] = None,
                 scan_opts: Optional["redactor_ScanOptions"] = None,
                 ) -> dict:
    """OCR every page of a PDF and return a redaction plan dict.

    Page images are rendered at *dpi*; OCR bounding boxes are converted from
    pixel space to PDF points (1 pt = 1/72 inch) before being stored.
    """
    from .redactor import ScanOptions
    pymupdf = _require_pymupdf()
    doc = pymupdf.open(str(pdf_path))
    plan = new_plan(pdf_path.name, "pdf", dpi=dpi, lang=lang)
    opts = scan_opts or ScanOptions()
    scale = dpi / 72.0
    detection_idx = 0

    with tempfile.TemporaryDirectory(prefix="ocr-redact-") as td:
        for pno, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            img_path = Path(td) / f"page-{pno:04d}.png"
            pix.save(str(img_path))
            try:
                words = run_ocr(img_path, lang=lang, tesseract_cmd=tesseract_cmd)
            except Exception as exc:
                plan["warnings"].append(f"Page {pno}: OCR failed — {exc}")
                continue
            entries, page_warnings = detect_on_ocr(words, scan_opts=opts)
            plan["warnings"].extend(page_warnings)
            for entry in entries:
                detection_idx += 1
                entry["id"] = f"d{detection_idx:05d}"
                entry["page"] = pno
                # Convert pixel bbox → PDF points
                l, t, r, b = entry["bbox"]
                entry["bbox"] = [
                    round(l / scale, 3), round(t / scale, 3),
                    round(r / scale, 3), round(b / scale, 3),
                ]
                entry["coordinate_space"] = "pdf_points"
                plan["detections"].append(entry)
    doc.close()
    return plan


def scan_ocr_image(image_path: Path, lang: str = "eng",
                   tesseract_cmd: Optional[str] = None,
                   scan_opts: Optional["redactor_ScanOptions"] = None,
                   ) -> dict:
    """OCR a standalone image and return a redaction plan."""
    from .redactor import ScanOptions
    opts = scan_opts or ScanOptions()
    plan = new_plan(image_path.name, "image", lang=lang)
    words = run_ocr(image_path, lang=lang, tesseract_cmd=tesseract_cmd)
    entries, warnings = detect_on_ocr(words, scan_opts=opts)
    plan["warnings"].extend(warnings)
    for i, entry in enumerate(entries, 1):
        entry["id"] = f"d{i:05d}"
        entry["page"] = 1
        entry["bbox"] = [round(float(x), 3) for x in entry["bbox"]]
    plan["detections"] = entries
    return plan


def apply_ocr_redactions(src: Path, plan: dict, out: Path) -> None:
    """Apply a redaction plan to a PDF or image."""
    if src.resolve() == out.resolve():
        raise RuntimeError("Refusing to overwrite the source file.")
    ext = src.suffix.lower()
    if ext in PDF_EXTS:
        apply_pdf_ocr_redactions(src, plan, out)
    elif ext in IMAGE_EXTS:
        apply_image_redactions(src, plan, out)
    else:
        raise RuntimeError(f"Unsupported type for OCR redaction: {ext}")


def verify_ocr(path: Path, dpi: int = 200, lang: str = "eng",
               tesseract_cmd: Optional[str] = None,
               scan_opts: Optional["redactor_ScanOptions"] = None,
               ) -> dict:
    """Re-scan a redacted output and report any remaining detections."""
    ext = path.suffix.lower()
    if ext in PDF_EXTS:
        plan = scan_ocr_pdf(path, dpi=dpi, lang=lang,
                            tesseract_cmd=tesseract_cmd, scan_opts=scan_opts)
    elif ext in IMAGE_EXTS:
        plan = scan_ocr_image(path, lang=lang,
                              tesseract_cmd=tesseract_cmd, scan_opts=scan_opts)
    else:
        return {"status": "ERROR", "error": f"Unsupported type: {ext}"}
    remaining = len(plan["detections"])
    return {
        "status": "PASS" if remaining == 0 and not plan["warnings"] else "NEEDS_REVIEW",
        "remaining_detection_count": remaining,
        "remaining_detections": plan["detections"],
        "warnings": plan["warnings"],
    }
