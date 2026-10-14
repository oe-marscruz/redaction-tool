"""Post-export recoverability checks.

A visual black box is not a redaction.  After export we re-extract text
from every representation we can reach and refuse to call the result
safely redacted if a targeted value is still recoverable.

This module never logs the recovered values themselves.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path


def _pdf_recoverable_text(path: Path) -> str:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore
    doc = fitz.open(str(path))
    parts: list[str] = []
    try:
        parts.append("\n".join(page.get_text() for page in doc))
        # Raw content streams — catches text that survived as un-applied
        # operators under a painted rectangle.
        for page in doc:
            try:
                parts.append(page.read_contents().decode("latin-1", errors="ignore"))
            except Exception:
                pass
        # Metadata
        try:
            md = doc.metadata or {}
            parts.extend(str(v) for v in md.values() if v)
        except Exception:
            pass
        # Link URIs and targets
        for page in doc:
            try:
                for lnk in page.get_links():
                    parts.append(str(lnk.get("uri") or ""))
                    parts.append(str(lnk.get("nameddest") or ""))
            except Exception:
                pass
        # Embedded files
        for i in range(doc.embfile_count()):
            try:
                data = doc.embfile_get(i) or b""
                parts.append(data.decode("latin-1", errors="ignore"))
            except Exception:
                pass
        # Widgets
        for page in doc:
            try:
                for w in page.widgets() or []:
                    parts.append(str(getattr(w, "field_value", "") or ""))
                    parts.append(str(getattr(w, "field_name", "") or ""))
            except Exception:
                pass
        # Annotations
        for page in doc:
            try:
                for annot in page.annots() or []:
                    info = annot.info or {}
                    parts.append(str(info.get("content") or ""))
                    parts.append(str(info.get("title") or ""))
            except Exception:
                pass
    finally:
        doc.close()
    return "\n".join(parts)


def _opc_recoverable_text(path: Path) -> str:
    """DOCX/XLSX: concatenate every XML part, including hidden ones."""
    chunks: list[str] = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            data = z.read(name)
            try:
                chunks.append(data.decode("utf-8"))
            except UnicodeDecodeError:
                chunks.append(data.decode("latin-1", errors="ignore"))
    return "\n".join(chunks)


def recoverable_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_recoverable_text(path)
    if ext in {".docx", ".xlsx"}:
        return _opc_recoverable_text(path)
    return ""


def values_still_present(path: Path, values: list[str]) -> list[str]:
    """Return the subset of *values* that can still be recovered.

    Comparison is case-insensitive.  Short values (< 4 chars) are skipped
    to avoid flagging residual 'May' / 'A.' fragments that are not the
    original identifier.
    """
    blob = recoverable_text(path).lower()
    leaked: list[str] = []
    for v in values:
        needle = (v or "").strip()
        if len(needle) < 4:
            continue
        if needle.lower() in blob:
            leaked.append(v)
    return leaked


def verify_export(
    path: Path,
    targeted_values: list[str] | None = None,
    scan_opts: object | None = None,
    use_ocr: bool = False,
) -> dict:
    """Fail-closed dual independent checks over final exported output.

    Check 1: targeted-value recoverability across all reachable parts.
    Check 2: fresh PII scan over final output representations.
    """
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return {
            "status": "ERROR",
            "reason": "output missing or empty — refusing to treat as redacted",
            "leaked_count": -1,
            "residual_count": -1,
            "warnings": ["output missing or empty"],
        }

    try:
        blob = recoverable_text(path)
    except Exception as exc:
        return {
            "status": "ERROR",
            "reason": f"unreadable or corrupt export file: {exc}",
            "leaked_count": -1,
            "residual_count": -1,
            "warnings": [f"Extraction failed: {exc}"],
        }

    leaked: list[str] = []
    if targeted_values:
        leaked = values_still_present(path, targeted_values)

    residual_matches: list = []
    scan_warnings: list[str] = []

    if scan_opts is not None:
        try:
            ext = path.suffix.lower()
            if ext in {".docx", ".xlsx", ".pdf"}:
                try:
                    from .redactor import iter_text_units
                    units = iter_text_units(path)
                    for u in units:
                        matches = getattr(scan_opts, "run_detection")(u)
                        residual_matches.extend(matches)
                except Exception:
                    matches = getattr(scan_opts, "run_detection")(blob)
                    residual_matches.extend(matches)
            elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
                from . import ocr as _ocr
                ocr_res = _ocr.verify_ocr(path, scan_opts=scan_opts)
                if ocr_res.get("status") in ("ERROR", "NEEDS_REVIEW"):
                    if ocr_res.get("status") == "ERROR":
                        return {
                            "status": "ERROR",
                            "reason": f"OCR verification error: {'; '.join(ocr_res.get('warnings', []))}",
                            "leaked_count": len(leaked),
                            "residual_count": -1,
                            "warnings": ocr_res.get("warnings", []),
                        }
                    scan_warnings.extend(ocr_res.get("warnings", []))
                    res_c = ocr_res.get("remaining_detection_count", 0)
                    if res_c > 0:
                        residual_matches.extend(["ocr_match"] * res_c)

            if ext == ".pdf" and use_ocr:
                from . import ocr as _ocr
                ocr_res = _ocr.verify_ocr(path, scan_opts=scan_opts)
                if ocr_res.get("status") == "ERROR":
                    return {
                        "status": "ERROR",
                        "reason": f"OCR verification error: {'; '.join(ocr_res.get('warnings', []))}",
                        "leaked_count": len(leaked),
                        "residual_count": -1,
                        "warnings": ocr_res.get("warnings", []),
                    }
                if ocr_res.get("warnings"):
                    scan_warnings.extend(ocr_res.get("warnings", []))
                ocr_count = ocr_res.get("remaining_detection_count", 0)
                if ocr_count > 0:
                    residual_matches.extend(["ocr_match"] * ocr_count)

        except Exception as exc:
            return {
                "status": "ERROR",
                "reason": f"fresh PII verification scan exception: {exc}",
                "leaked_count": len(leaked),
                "residual_count": -1,
                "warnings": [f"Verification scan exception: {exc}"],
            }

    residual_count = len(residual_matches)
    if leaked or residual_count > 0 or scan_warnings:
        reasons: list[str] = []
        if leaked:
            reasons.append(f"{len(leaked)} targeted value(s) recoverable from export")
        if residual_count > 0:
            reasons.append(f"{residual_count} residual PII detection(s) found on output")
        if scan_warnings:
            reasons.append(f"verification warning(s): {'; '.join(scan_warnings)}")
        return {
            "status": "NEEDS_REVIEW",
            "reason": "; ".join(reasons),
            "leaked_count": len(leaked),
            "residual_count": residual_count,
            "warnings": scan_warnings,
        }

    return {
        "status": "PASS",
        "reason": "targeted values and residual PII not recoverable from extractable representations",
        "leaked_count": 0,
        "residual_count": 0,
        "warnings": [],
    }
