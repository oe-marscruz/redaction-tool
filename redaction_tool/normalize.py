"""PASS 0 — canonical text normalization with original-offset mapping.

Detectors that need OCR/hyphenation tolerance run on the normalized view
and map spans back to the source so redaction still hits the real text.
"""

from __future__ import annotations

import unicodedata

# Hyphen-like code points collapsed to ASCII hyphen.
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"), ord("-"))
# Interpuncts / bullet-separators used as date separators ("05·14·2002").
_DASHES.update(dict.fromkeys(map(ord, "\u00b7\u2027\u22c5\u2219\uff65\u00b8"), ord("-")))
# Spaces collapsed to ASCII space (but newlines kept until hyphen-join).
_SPACES = dict.fromkeys(map(ord, "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"), ord(" "))


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_DASHES).translate(_SPACES)


def build_normalized(text: str) -> tuple[str, list[int]]:
    """Return (normalized_text, orig_index_for_each_norm_char).

    Operations:
    * NFKC + dash/space canonicalization
    * Join hyphenated line-wraps: ``Mar-\\n garet`` → ``Margaret``
    * Collapse runs of whitespace (except keeping a single space)
    * Drop zero-width characters

    The orig-index list is the same length as normalized_text.  A span
    [s, e) in normalized text maps to original [index[s], index[e-1]+1).
    """
    src = nfkc(text)
    out: list[str] = []
    index: list[int] = []
    i = 0
    n = len(src)
    prev_was_space = False
    while i < n:
        ch = src[i]
        o = ord(ch)
        if o in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x2060):
            i += 1
            continue
        # Hyphenated wrap: letter, hyphen, optional space, newline, optional space, letter
        if ch == "-" and out and out[-1].isalpha():
            j = i + 1
            while j < n and src[j] in " \t":
                j += 1
            if j < n and src[j] in "\r\n":
                j += 1
                if j < n and src[j] == "\n":
                    j += 1
                while j < n and src[j] in " \t":
                    j += 1
                if j < n and src[j].isalpha():
                    i = j
                    prev_was_space = False
                    continue
        if ch in " \t\r\n":
            if not prev_was_space and out:
                out.append(" ")
                index.append(i)
            prev_was_space = True
            i += 1
            continue
        out.append(ch)
        index.append(i)
        prev_was_space = False
        i += 1
    return "".join(out), index


def map_span(index: list[int], start: int, end: int, orig_len: int) -> tuple[int, int]:
    """Map a normalized [start, end) span back to original coordinates."""
    if not index or start >= end:
        return 0, 0
    start = max(0, min(start, len(index) - 1))
    end_i = min(end, len(index)) - 1
    orig_start = index[start]
    orig_end = index[end_i] + 1
    return orig_start, min(orig_end, orig_len)


# OCR confusable substitutions applied only to *candidate generation*
# for already-known entity strings, never as a global text rewrite.
_OCR_CONFUSABLES = {
    "0": "O",
    "O": "0",
    "1": "I",
    "I": "1",
    "l": "1",
    "5": "S",
    "S": "5",
    "8": "B",
    "B": "8",
}


def ocr_variants(value: str, max_variants: int = 12) -> list[str]:
    """Generate a small set of OCR-confused spellings of *value*."""
    if not value or len(value) > 48:
        return []
    seen = {value}
    variants = [value]
    # Single-position substitutions.
    for i, ch in enumerate(value):
        repl = _OCR_CONFUSABLES.get(ch)
        if not repl:
            continue
        candidate = value[:i] + repl + value[i + 1:]
        if candidate not in seen:
            seen.add(candidate)
            variants.append(candidate)
            if len(variants) >= max_variants:
                break
    # rn ↔ m
    if "m" in value and len(variants) < max_variants:
        variants.append(value.replace("m", "rn", 1))
    if "rn" in value and len(variants) < max_variants:
        variants.append(value.replace("rn", "m", 1))
    return variants[1:]  # exclude the original
