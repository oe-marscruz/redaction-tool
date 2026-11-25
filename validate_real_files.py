"""Validate the Redaction Tool against a local document corpus.

Usage:
    python validate_real_files.py FILE [FILE ...] \
        [--must-not-leak "First Last"] [--must-not-leak "Surname"] ...

Every input is copied into a scratch directory before redaction, so originals
are never modified.  For each file the tool reports the detections, applies the
redaction, and checks that none of the ``--must-not-leak`` strings survive in
the extracted text of the output.

Never point this at real case files while developing or in CI — use synthetic
files only (see tests/ for generators).  Redacted output is written to
``<tempdir>/redaction_validate_out`` and can be inspected or deleted freely.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from redaction_tool import redactor  # noqa: E402

OUT = Path(tempfile.gettempdir()) / "redaction_validate_out"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Redact local documents and check that identifiers are gone.")
    parser.add_argument("files", nargs="+", metavar="FILE",
                        help="PDF, DOCX or XLSX files to validate")
    parser.add_argument("--must-not-leak", action="append", default=[],
                        metavar="TEXT",
                        help="string that must not survive redaction (repeatable); "
                             "also added to the detector's extra literal texts")
    args = parser.parse_args(argv)

    opts = redactor.ScanOptions(
        enabled_categories=None,      # Full preset (all 19 categories)
        custom_texts=list(args.must_not_leak),
    )

    OUT.mkdir(parents=True, exist_ok=True)
    failures = []
    for src in (Path(f).expanduser() for f in args.files):
        print("=" * 78)
        print("SRC:", src.name)
        if not src.is_file():
            print("  MISSING — skipping")
            failures.append(src.name)
            continue

        try:
            raw_text = redactor.extract_text(src)
            counts = redactor.scan_file(src, opts)
        except Exception as exc:  # noqa: BLE001
            print("  SCAN ERROR:", exc)
            failures.append(src.name)
            continue
        print(f"  extractable text: {len(raw_text)} chars"
              + ("  <-- IMAGE-ONLY (no text layer)" if len(raw_text.strip()) < 20 else ""))
        print(f"  detections: {sum(counts.values())}")
        for cat, n in sorted(counts.items()):
            print(f"    {cat}: {n}")

        result = redactor.redact_file(src, opts, out_dir=OUT)
        if result.error:
            print("  REDACT ERROR:", result.error)
            failures.append(src.name)
            continue
        print(f"  redactions applied: {result.redaction_count}")
        for output in result.outputs:
            print(f"    wrote: {output}")

        if not result.outputs:
            print("  ERROR: no output file was produced")
            failures.append(src.name)
            continue
        redacted_text = redactor.extract_text(result.outputs[0])
        leaks = [s for s in args.must_not_leak if s.lower() in redacted_text.lower()]
        if leaks:
            print("  LEAK:", leaks)
            low = redacted_text.lower()
            for leak in leaks:
                idx = low.find(leak.lower())
                print("    context:", repr(redacted_text[max(0, idx - 60):idx + 60]))
            failures.append(src.name)
        else:
            print("  OK — no subject identifiers remain in extracted text")

    print("=" * 78)
    print("RESULT:", "FAIL: " + ", ".join(failures) if failures else "ALL PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
