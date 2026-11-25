"""Batch-scoped pseudonym labels for qualitative coding.

Redacting every identifier to the same ``[REDACTED]`` keeps a corpus safe but
destroys the analyst's ability to follow one person or one account through a
case file.  This module maps each detected *value* to a stable, typed label
(``[NAME_1]``, ``[EMAIL_1]``, ``[SSN_1]``) for the lifetime of a batch, so the
same subject reads the same way in every document.

The mapping is deliberately in-memory only: a value→label table written to disk
would be a plaintext PII index, which is exactly what the tool exists to avoid.
Labels are derived from category tags, never from the value itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Short, human-readable tag per detector category.  Unknown keys fall back to
# REDACTED so a new taxonomy entry still produces a stable label.
CATEGORY_TAGS: dict[str, str] = {
    "names": "NAME",
    "addresses": "ADDRESS",
    "dates": "DATE",
    "phones": "PHONE",
    "fax": "FAX",
    "emails": "EMAIL",
    "ssn": "SSN",
    "mrn": "MRN",
    "health_plan": "HEALTHPLAN",
    "accounts": "ACCOUNT",
    "licenses": "LICENSE",
    "vehicles": "VEHICLE",
    "devices": "DEVICE",
    "urls": "URL",
    "ips": "IP",
    "biometric": "BIOMETRIC",
    "unique_ids": "ID",
    "student_records": "STUDENTRECORD",
    "financial": "FINANCIAL",
    "custom": "CUSTOM",
}


def _key(category: str, value: str) -> tuple[str, str]:
    return category, " ".join(value.split()).casefold()


@dataclass
class Pseudonymizer:
    """Assign one label per (category, value) pair across a whole batch."""

    prefix: str = "["
    suffix: str = "]"
    labels: dict[tuple[str, str], str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def label_for(self, category: str, value: str) -> str:
        key = _key(category, value)
        existing = self.labels.get(key)
        if existing is not None:
            return existing
        tag = CATEGORY_TAGS.get(category, "REDACTED")
        next_index = self.counters.get(tag, 0) + 1
        self.counters[tag] = next_index
        label = f"{self.prefix}{tag}_{next_index}{self.suffix}"
        self.labels[key] = label
        return label

    def used_labels(self) -> list[str]:
        """Labels in assignment order (no source values)."""
        return list(self.labels.values())
