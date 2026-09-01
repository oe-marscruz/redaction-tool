"""High-recall date and age-over-89 detection.

Absolute calendar dates, written dates, month-day without year, two-digit
years, and relative temporal expressions.  Policy (remove vs. generalize to
year) is applied by the caller, not here.
"""

from __future__ import annotations

import re

_MONTH = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?"
)

_WEEKDAY = r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Tues|Wed|Thu|Thur|Thurs|Fri|Sat|Sun"

_ORDINAL_NUM = r"\d{1,2}(?:st|nd|rd|th)"

_WRITTEN_DAY = (
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|"
    r"eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|"
    r"seventeenth|eighteenth|nineteenth|twentieth|twenty[-\s]first|"
    r"twenty[-\s]second|twenty[-\s]third|twenty[-\s]fourth|"
    r"twenty[-\s]fifth|twenty[-\s]sixth|twenty[-\s]seventh|"
    r"twenty[-\s]eighth|twenty[-\s]ninth|thirtieth|thirty[-\s]first"
)

_YEAR4 = r"(?:19|20)\d{2}"
_YEAR2 = r"\d{2}"

# Optional spaces around separators (OCR: "04 / 17 / 2026").
_S = r"[\s]*"

_MDY_NUM = (
    rf"\b(?:0?[1-9]|1[0-2]){_S}[/\-.]{_S}(?:0?[1-9]|[12]\d|3[01])"
    rf"(?:{_S}[/\-.]{_S}(?:{_YEAR4}|{_YEAR2}))?\b"
)

# Zero-padded MM/DD without year — less likely to be a ratio.
_MD_PADDED = r"\b(?:0[1-9]|1[0-2])[/\-](?:0[1-9]|[12]\d|3[01])\b"

_ISO = rf"\b{_YEAR4}{_S}[/\-.]{_S}(?:0?[1-9]|1[0-2]){_S}[/\-.]{_S}(?:0?[1-9]|[12]\d|3[01])\b"

_MONTH_DAY_YEAR = (
    rf"\b(?:{_MONTH})\.?{_S}(?:{_ORDINAL_NUM}|\d{{1,2}}|{_WRITTEN_DAY})"
    rf"(?:,)?{_S}(?:{_YEAR4}|{_YEAR2})?\b"
)

_DAY_MONTH_YEAR = (
    rf"\b(?:{_ORDINAL_NUM}|\d{{1,2}})\s+(?:{_MONTH})\.?"
    rf"(?:,)?(?:\s+(?:{_YEAR4}|{_YEAR2}))?\b"
)

_DAY_MON_YY = (
    rf"\b(?:0?[1-9]|[12]\d|3[01])[- ](?:{_MONTH})[- ](?:{_YEAR4}|{_YEAR2})\b"
)

_WRITTEN_FULL = (
    rf"\b(?:{_MONTH})\s+({_WRITTEN_DAY})\b"
)

_THE_OF = (
    rf"\bthe\s+(?:{_ORDINAL_NUM}|{_WRITTEN_DAY}|\d{{1,2}})\s+of\s+(?:{_MONTH})"
    rf"(?:,?\s+(?:{_YEAR4}))?\b"
)

_RELATIVE = (
    rf"\b(?:yesterday|tomorrow)\b|"
    rf"\b(?:last|next|this)\s+(?:{_WEEKDAY}|week|month|year)\b|"
    rf"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
    rf"\s+(?:days?|weeks?|months?|years?)\s+ago\b"
)

_DOB_LABEL = (
    rf"\b(?:DOB|D\.O\.B\.?|Date\s+of\s+Birth|Birth\s*date|Born)\s*[:\-–—]?\s*"
)

_AGE_OVER_89 = (
    r"\b(?:age|aged)[:\s]*(?:9\d|1\d{2})\b|"
    r"\b(?:9\d|1\d{2})\s*(?:years?\s+old|y/?o)\b"
)

# Context words that make an unpadded MM/DD (no year) more likely a date.
_DATE_CONTEXT = re.compile(
    r"(?i)\b(?:on|admitted|admission|discharged|discharge|dob|born|"
    r"appointment|procedure|surgery|exam|hearing|enrolled|enrollment|"
    r"lab|imaging|collected|seen|visited|follow[-\s]?up|scheduled|"
    r"died|death|deceased|incident|occurred|effective|dated)\b"
)


def _c(pat: str, flags: int = 0) -> re.Pattern:
    return re.compile(pat, re.MULTILINE | flags | re.IGNORECASE)


_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_c(_THE_OF), "written_the_of"),
    (_c(_WRITTEN_FULL), "written_month_day"),
    (_c(_DAY_MON_YY), "d_mon_yy"),
    (_c(_MONTH_DAY_YEAR), "month_day_year"),
    (_c(_DAY_MONTH_YEAR), "day_month_year"),
    (_c(_ISO), "iso"),
    (_c(_MDY_NUM), "numeric"),
    (_c(_MD_PADDED), "md_padded"),
    (_c(_RELATIVE), "relative"),
    (_c(_AGE_OVER_89), "age_over_89"),
]


def _valid_numeric_date(text: str) -> bool:
    """Reject impossible days/months and bare ratios like 5/97."""
    compact = re.sub(r"\s+", "", text)
    m = re.match(
        r"^(?:(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?|"
        r"(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2}))$",
        compact,
    )
    if not m:
        return True  # non-numeric (month names, relative) — keep
    if m.group(4):
        month, day = int(m.group(5)), int(m.group(6))
    else:
        month, day = int(m.group(1)), int(m.group(2))
        year = m.group(3)
        if year is None:
            # MM/DD no year — require a plausible month/day
            pass
        elif len(year) == 2:
            pass
        elif len(year) == 4:
            y = int(year)
            if y < 1900 or y > 2100:
                return False
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    return True


def _looks_like_ratio(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    return bool(re.fullmatch(r"\d{1,3}/\d{1,3}", compact)) and "/" in compact \
        and not re.fullmatch(r"(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])", compact)


def _looks_like_version(text: str, following: str) -> bool:
    """Reject dotted numeric fragments that are software versions (1.2.3)."""
    compact = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d{1,2}\.\d{1,2}", compact) and following.startswith("."):
        return True
    # A 4-digit (or 2-digit) year-shaped final component is a date like
    # 04.17.2026, not a version like 1.2.3 — do not reject.
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.(?:19|20)\d{2}", compact):
        return False
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{1,4}", compact):
        return True
    return False


def detect_dates(text: str, *, include_relative: bool = True) -> list[tuple[int, int, str, str]]:
    """Return (start, end, matched_text, evidence)."""
    hits: list[tuple[int, int, str, str]] = []
    for pat, evidence in _PATTERNS:
        if evidence == "relative" and not include_relative:
            continue
        for m in pat.finditer(text):
            val = m.group()
            if evidence in {"numeric", "md_padded", "iso"} and not _valid_numeric_date(val):
                continue
            if _looks_like_version(val, text[m.end():m.end() + 4]):
                continue
            if evidence == "numeric" and _looks_like_ratio(val):
                # Unpadded MM/DD without year: keep only with nearby date context.
                window = text[max(0, m.start() - 40):m.end() + 10]
                if not _DATE_CONTEXT.search(window):
                    continue
            # Dotted MM.DD with no year is almost always a version/section number
            # unless date context is nearby.
            compact = re.sub(r"\s+", "", val)
            if evidence == "numeric" and re.fullmatch(r"\d{1,2}\.\d{1,2}", compact):
                window = text[max(0, m.start() - 40):m.end() + 10]
                if not _DATE_CONTEXT.search(window):
                    continue
            hits.append((m.start(), m.end(), val, evidence))
    return hits
