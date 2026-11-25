"""Per-document redaction audit trail.

The JSON batch log has always carried per-category counts.  Compliance review
needs more: *where* inside the document each category was removed, so a
reviewer can open the output at that page / sheet cell / paragraph and
spot-check.  This module records those locations.

Rules:
  * Locations are structural labels only ("page 3", "Roster!B12", "body ¶7").
  * Values are never stored — only categories and counts — so the log and the
    rendered report remain free of plaintext PII.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class RedactionAudit:
    """Category counts keyed by structural location, in first-seen order."""

    units: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, where: str, category: str, count: int = 1) -> None:
        cats = self.units.setdefault(where, {})
        cats[category] = cats.get(category, 0) + count

    def as_list(self) -> list[dict]:
        return [
            {"where": where, "categories": dict(sorted(cats.items()))}
            for where, cats in self.units.items()
        ]

    def category_totals(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for cats in self.units.values():
            for category, count in cats.items():
                totals[category] = totals.get(category, 0) + count
        return dict(sorted(totals.items()))


def _format_categories(cats: dict[str, int]) -> str:
    return ", ".join(f"{name} ×{count}" if count > 1 else name
                     for name, count in sorted(cats.items()))


def _unique_path(path: Path) -> Path:
    """Avoid overwriting a log or report written by another batch in the same second."""
    if not path.exists():
        return path
    for n in range(2, 100):
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path


def write_batch_artifacts(base: Path, batch: dict) -> tuple[Path, Path]:
    """Write ``redaction_log_*.json`` and ``redaction_report_*.md`` into *base*.

    Returns (log_path, report_path).  Neither file contains source values.
    """
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = _unique_path(base / f"redaction_log_{stamp}.json")
    log_path.write_text(json.dumps(batch, indent=2), encoding="utf-8")
    report_path = _unique_path(base / f"redaction_report_{stamp}.md")
    report_path.write_text(render_markdown(batch), encoding="utf-8")
    return log_path, report_path


def render_markdown(batch: dict) -> str:
    """Render a batch log dict (the JSON written next to the outputs) as Markdown."""
    entries = batch.get("entries", [])
    stamp = batch.get("generated_at") or datetime.now().isoformat(timespec="seconds")
    mode = "typed pseudonym labels" if batch.get("pseudonymize") else \
        f'constant replacement "{batch.get("replacement", "")}"'

    lines: list[str] = [
        "# Redaction report",
        "",
        f"- Generated: {stamp}",
        f"- Tool version: {batch.get('tool_version', 'unknown')}",
        f"- Preset: {batch.get('preset', 'unknown')}",
        f"- Replacement: {mode}",
        f"- Presidio NER: {'on' if batch.get('use_presidio') else 'off'}",
        "- This report contains categories and locations only — no source text.",
        "",
        "## Batch summary",
        "",
    ]

    ok = sum(1 for e in entries if e.get("verify", {}).get("status") == "PASS"
             and not e.get("errors"))
    needs_review = len(entries) - ok
    total_redactions = sum(int(e.get("redaction_count") or 0) for e in entries)
    totals: dict[str, int] = {}
    for entry in entries:
        for category, count in (entry.get("per_category") or {}).items():
            totals[category] = totals.get(category, 0) + int(count)

    lines += [
        f"- Documents: {len(entries)} ({ok} PASS, {needs_review} need review)",
        f"- Redactions applied: {total_redactions}",
        f"- Categories: {_format_categories(totals) if totals else 'none'}",
        "",
        "## Documents",
        "",
    ]

    for entry in entries:
        name = entry.get("source") or "(unknown)"
        lines.append(f"### {name}")
        lines.append("")
        verify = entry.get("verify") or {}
        status = verify.get("status") or ("ERROR" if entry.get("errors") else "not verified")
        residual = verify.get("residual")
        detail = f"- Verify: {status}"
        if residual is not None:
            detail += f" (residual detections: {residual})"
        lines.append(detail)
        if entry.get("recoverability"):
            lines.append(f"- Recoverability: {entry['recoverability']}"
                         + (f" (leaked values: {entry['recoverability_leaked']})"
                            if entry.get("recoverability_leaked") else ""))
        lines.append(f"- Redactions: {entry.get('redaction_count', 0)}")
        for out in entry.get("outputs") or []:
            lines.append(f"- Output: {out}")
        for err in entry.get("errors") or []:
            lines.append(f"- **Problem:** {err}")
        audit = entry.get("audit") or []
        if audit:
            lines += ["", "| Where | Categories |", "|---|---|"]
            for unit in audit:
                lines.append(f"| {unit['where']} | {_format_categories(unit['categories'])} |")
        lines.append("")

    failing = [e for e in entries if e.get("errors")
               or (e.get("verify") or {}).get("status") not in (None, "PASS")]
    if failing:
        lines += ["## Follow-up required", ""]
        for entry in failing:
            reason = "; ".join(entry.get("errors") or []) or \
                f"verify {((entry.get('verify') or {}).get('status'))}"
            lines.append(f"- {entry.get('source')}: {reason}")
        lines.append("")

    lines += [
        "---",
        "",
        "Automated detection is not a compliance certification. Spot-check each",
        "output before relying on it; scanned pages without OCR produce no",
        "text-layer detections.",
        "",
    ]
    return "\n".join(lines)
