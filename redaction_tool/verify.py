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
        # Link URIs
        for page in doc:
            for lnk in page.get_links():
                parts.append(str(lnk.get("uri") or ""))
                parts.append(str(lnk.get("nameddest") or ""))
        # Embedded files
        for i in range(doc.embfile_count()):
            try:
                data = doc.embfile_get(i) or b""
                parts.append(data.decode("latin-1", errors="ignore"))
            except Exception:
                pass
        # Widgets
        for page in doc:
            for w in page.widgets() or []:
                parts.append(str(getattr(w, "field_value", "") or ""))
                parts.append(str(getattr(w, "field_name", "") or ""))
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


def verify_export(path: Path, targeted_values: list[str]) -> dict:
    """Fail-closed check: any recoverable targeted value → NEEDS_REVIEW."""
    if not path.exists() or path.stat().st_size == 0:
        return {
            "status": "ERROR",
            "reason": "output missing or empty — refusing to treat as redacted",
            "leaked_count": -1,
        }
    leaked = values_still_present(path, targeted_values)
    if leaked:
        return {
            "status": "NEEDS_REVIEW",
            "reason": "targeted values recoverable from export",
            "leaked_count": len(leaked),
        }
    return {
        "status": "PASS",
        "reason": "targeted values not recoverable from extractable representations",
        "leaked_count": 0,
    }
