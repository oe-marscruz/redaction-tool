"""Document-level entity memory.

If "Alexandria Montoya" is identified once, later mentions such as
"Alexandria", "Ms. Montoya", "Montoya", and "A. Montoya" are treated as
the same person.  Variants are matched case-sensitively for short/common
tokens to avoid turning "the brown folder" into a hit for "Brown".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .normalize import ocr_variants

_HONORIFICS = ("Mr.", "Mrs.", "Ms.", "Miss", "Dr.", "Prof.", "Mx.")

_COMMON_LAST = frozenset({
    "street", "avenue", "road", "drive", "lane", "court", "monday", "tuesday",
    "wednesday", "thursday", "friday", "saturday", "sunday", "january",
    "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "university", "college", "hospital",
    "clinic", "office", "school", "summary", "report", "record", "patient",
    "student", "parent", "brown", "green", "white", "black", "gray", "grey",
    "young", "long", "short", "little", "best", "west", "north", "south",
    "east", "park", "hill", "wood", "hall", "king", "gold", "stone",
})

_COMMON_FIRST = frozenset({
    "may", "june", "april", "august", "grace", "hope", "faith", "joy",
    "ruby", "iris", "olive", "rose", "lily", "amber", "crystal", "dawn",
    "summer", "autumn", "jordan", "morgan", "taylor", "casey", "avery",
    "payton", "peyton", "riley", "reagan", "quinn", "rowen", "rowan",
})

_PARTICLES = frozenset({
    "de", "da", "di", "do", "del", "della", "dei", "des", "du", "la", "le",
    "los", "las", "van", "von", "el", "al", "bin", "ibn", "ten", "ter",
    "den", "der", "dos", "das", "st", "st.",
})


def _tokens(name: str) -> list[str]:
    cleaned = re.sub(r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof(?:essor)?|Mx|Sir|Madam|Rev|Hon)\.?\s+",
                     "", name, flags=re.I)
    parts = re.split(r"[\s,]+", cleaned.strip())
    return [p for p in parts if p and p.lower().strip(".") not in _PARTICLES]


@dataclass
class EntityLedger:
    """In-memory, process-local.  Never logged."""

    names: set[str] = field(default_factory=set)
    _variants: set[str] = field(default_factory=set)

    def ingest(self, name: str) -> None:
        name = " ".join(name.split())
        if len(name) < 2:
            return
        self.names.add(name)
        self._variants.add(name)
        toks = _tokens(name)
        if not toks:
            return
        first, last = toks[0].rstrip("."), toks[-1].rstrip(".")
        # Drop trailing middle initials from last if we grabbed "A." as last.
        if last.endswith(".") and len(last) <= 2 and len(toks) >= 2:
            last = toks[-2].rstrip(".")
        if len(first) >= 3:
            self._variants.add(first)
            self._variants.add(first + "'s")
            self._variants.add(first + "’s")
        if len(last) >= 3:
            # Capitalized last-name only; skip lowercase common words.
            if last.lower() not in _COMMON_LAST or last[0].isupper():
                if last.lower() not in _COMMON_LAST:
                    self._variants.add(last)
                    self._variants.add(last + "'s")
                elif last[0].isupper() and last.lower() not in {"may", "june", "april"}:
                    # Still propagate Title-Case common surnames (Brown) but
                    # matching is later required to be Title-Case / ALL-CAPS.
                    self._variants.add(last)
            for hon in _HONORIFICS:
                self._variants.add(f"{hon} {last}")
            if first:
                initial = re.sub(r"[^A-Za-z]", "", first)[:1]
                if initial:
                    self._variants.add(f"{initial}. {last}")
                    self._variants.add(f"{initial} {last}")
        if len(toks) >= 2:
            self._variants.add(f"{first} {last}")
            self._variants.add(f"{last}, {first}")
        for v in list(self._variants):
            if 3 <= len(v) <= 40:
                for ocr_v in ocr_variants(v, max_variants=6):
                    self._variants.add(ocr_v)

    def ingest_many(self, names: list[str]) -> None:
        for n in names:
            self.ingest(n)

    def variants(self) -> list[str]:
        # Longest first so "Alexandria Montoya" wins over "Alexandria".
        return sorted(self._variants, key=lambda s: (-len(s), s.lower()))

    def extra_spans(self, text: str) -> list[tuple[int, int, str]]:
        """Find variant occurrences in *text*.  Conservative for short tokens."""
        spans: list[tuple[int, int, str]] = []
        for variant in self.variants():
            if len(variant) < 2:
                continue
            # Common first names (May, Jordan) as standalone require Title Case
            # and are only emitted if the variant itself is Title Case.
            flags = 0
            if len(variant) <= 4 or variant.lower() in _COMMON_FIRST or variant.lower() in _COMMON_LAST:
                # Case-sensitive: "brown folder" must not match "Brown".
                pat = re.compile(rf"\b{re.escape(variant)}\b")
            else:
                pat = re.compile(rf"\b{re.escape(variant)}\b", re.IGNORECASE)
            for m in pat.finditer(text):
                spans.append((m.start(), m.end(), m.group()))
        return spans
