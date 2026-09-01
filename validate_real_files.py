"""Validate the Redaction Tool against real project documents.

Writes all outputs to the scratchpad — originals are never modified.
Checks that known PII (subject names from the filenames) is gone from the
redacted output text, and reports detection counts.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from redaction_tool import redactor  # noqa: E402

PROJECT = Path(__file__).parent.parent
OUT = Path(tempfile.gettempdir()) / "redaction_validate_out"
OUT.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION — edit these to match your own document corpus.
# ═══════════════════════════════════════════════════════════════════════════

TEST_FILES = [
    PROJECT / "path/to/sample_document.docx",
    PROJECT / "path/to/sample_document.pdf",
    PROJECT / "path/to/sample_spreadsheet.xlsx",
]

# Case-subject names or exact strings that must NOT appear in any redacted
# output.  Add one string per list entry — these are matched as whole words
# (case-insensitive).  The tool's custom_texts below should include at
# least these entries plus any nicknames.
MUST_NOT_LEAK = [
    # "First Last",      # ← add full names of case subjects
    # "Lastname",         # ← add surnames if they appear standalone
]

opts = redactor.ScanOptions(
    enabled_categories=None,  # Full preset (all 19 categories)
    custom_texts=[
        # "First Last",      # ← same entries as MUST_NOT_LEAK
        # "Nickname",        # ← add nicknames / short forms
    ],
)

failures = []
for src in TEST_FILES:
    print("=" * 78)
    print("SRC:", src.name)
    if not src.exists():
        print("  MISSING — skipping")
        continue

    # 1. Scan
    try:
        raw_text = redactor.extract_text(src)
        counts = redactor.scan_file(src, opts)
    except Exception as exc:
        print("  SCAN ERROR:", exc)
        failures.append(src.name)
        continue
    print(f"  extractable text: {len(raw_text)} chars"
          + ("  <-- IMAGE-ONLY (no text layer)" if len(raw_text.strip()) < 20 else ""))
    print(f"  detections: {sum(counts.values())}")
    for cat, n in sorted(counts.items()):
        print(f"    {cat}: {n}")

    # 2. Redact into scratchpad
    result = redactor.redact_file(src, opts, out_dir=OUT)
    if result.error:
        print("  REDACT ERROR:", result.error)
        failures.append(src.name)
        continue
    print(f"  redactions applied: {result.redaction_count}")
    for o in result.outputs:
        print(f"    wrote: {o}")

    # 3. Verify no leaks
    out_path = result.outputs[0]
    redacted_text = redactor.extract_text(out_path)
    leaks = [s for s in MUST_NOT_LEAK if s.lower() in redacted_text.lower()]
    if leaks:
        print("  LEAK:", leaks)
        # Show surrounding context for diagnosis
        low = redacted_text.lower()
        for leak in leaks:
            idx = low.find(leak.lower())
            print("    context:", repr(redacted_text[max(0, idx - 60):idx + 60]))
        failures.append(src.name)
    else:
        print("  OK — no subject identifiers remain in extracted text")

print("=" * 78)
print("RESULT:", "FAIL: " + ", ".join(failures) if failures else "ALL PASS")
