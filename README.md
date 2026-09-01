# Redaction Tool — FERPA / HIPAA

A local desktop tool that **permanently redacts** protected information from
**PDF, DOCX, and XLSX** documents. Everything runs on your machine — nothing
is uploaded anywhere, unlike Adobe Acrobat online services or ChatGPT.
Includes **light and dark mode** (toggle in the top-right corner; your choice
is remembered between sessions via `%USERPROFILE%\.redaction_tool\settings.json`).

## What it detects

Detection categories are based on the
[18 HIPAA identifiers](https://cphs.berkeley.edu/hipaa/hipaa18.html) and
[FERPA-protected information](https://it.cornell.edu/ferpa-and-it/information-protected-ferpa):

| Category | HIPAA # | Notes |
|---|---|---|
| Names | 1 | Honorifics ("Dr. Jane Smith"), built-in list of 500+ common first names ("First Last", "Last, First", standalone first names), email-closing words excluded. |
| Addresses / ZIP / City, State | 2 | Street addresses, PO boxes, ZIP/ZIP+4, city + state, apt/suite numbers. |
| Dates | 3 | All date formats + ages over 89. |
| Phone numbers | 4 | US formats incl. +1 prefix. |
| Fax numbers | 5 | Contextual ("Fax: …"). |
| Email addresses | 6 | |
| Social Security Numbers | 7 | Dashed / spaced / labeled. |
| Medical Record Numbers | 8 | Contextual ("MRN: …"). |
| Health Plan / Beneficiary Numbers | 9 | Contextual, must contain a digit. |
| Account Numbers | 10 | Contextual, must contain a digit. |
| Certificate / License Numbers | 11 | Incl. driver's license. |
| Vehicle Identifiers / VINs / Plates | 12 | Contextual. |
| Device / Serial / MAC Addresses | 13 | |
| URLs | 14 | |
| IP Addresses | 15 | IPv4. |
| Biometric references | 16 | Text references only. |
| Unique IDs | 18 | Student/Employee/Case/File numbers, bare 7–10 digit identifiers. |
| Student records (FERPA) | — | GPA, grades. |
| Financial info (FERPA/GLBA) | — | Tuition, aid, salary, etc. with $ amounts. |

**HIPAA #17 (full-face photos) cannot be auto-detected.** Review PDFs
manually; the tool leaves embedded images intact.

## Presets

- **FERPA Only** — student-focused categories.
- **HIPAA Only** — all 18 identifier categories.
- **Full (FERPA + HIPAA)** — everything.
- **Maximum / Strict** — every category, recall-first (highest false-positive
  tolerance, for cases where missing an identifier is worse than over-redacting).
- **Custom** — use *Customize / Save Preset…* to toggle categories and save
  your own profiles (stored in `%USERPROFILE%\.redaction_tool\presets`).

For known subjects (e.g. case respondents), paste their full names into the
**Extra literal texts** box — one per line. This is the most reliable way to
catch every occurrence, including nicknames. Advanced users can add regex
patterns, one per line.

## How redaction works

- **PDF**: PyMuPDF redaction annotations — matched text is *removed from the
  content stream*, not just covered with a black box. Document metadata
  (author, etc.) is scrubbed. Optionally renders each page to PNG/JPEG images.
- **DOCX**: matched text is replaced with `[REDACTED]` in-place, preserving
  surrounding formatting; headers, footers, tables, and core properties are
  also processed.
- **XLSX**: matched cell text is replaced with `[REDACTED]`; workbook
  properties are scrubbed. **Header-aware**: columns labeled `First Name`,
  `Last Name`, `Supervisor Name`, `Email`, `Phone`, `SSN`, `DOB`, `Address`,
  `ZIP`, `Empl ID`, etc. have *every value beneath the header* redacted —
  including numeric IDs and structured dates that text patterns can't reach.

Originals are **never modified**. Output files are written as
`<name>_REDACTED.<ext>` next to the source or into a chosen output folder.
The tool refuses to write output over the source file.

## Quick start — no install required

1. [Download **RedactionTool.exe** from the latest Release](https://github.com/oe-marscruz/redaction-tool/releases/latest)
2. Double-click it. That's it.

The exe is a **fully self-contained single-file build** — the Python
runtime and every dependency are bundled inside. Nothing to install, no
network access needed. This is the safest option for sensitive data.

Validate the exe on any machine (headless, writes `OK`/`FAIL`):

```
RedactionTool.exe --selftest result.txt
```

## Run from source (alternative)

If you cloned the repo and don't have the exe, double-click
**`Run-RedactionTool.bat`** — it creates a venv and **auto-installs any
missing dependencies** before launching. Manual equivalent:

```bash
cd redaction-tool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

To build your own exe after making changes:

```bash
pip install pyinstaller
pyinstaller --noconfirm RedactionTool.spec
```

> Note: single-file exe builds are occasionally flagged by antivirus
> heuristics (a known PyInstaller false positive). If that happens, build
> folder mode instead: `pyinstaller --noconfirm --onedir run.py`.

Run the headless self-test from source:

```bash
python run.py --selftest result.txt
```

## Important compliance notes

1. **Always manually review the scan counts before redacting**, and spot-check
   the output afterwards. Regex-based detection trades precision for recall:
   the "Full" preset deliberately over-redacts rather than under-redact, but
   no automated tool is a substitute for human review under FERPA/HIPAA.
2. Structured date columns in Excel (e.g. `Start Date`) are preserved by
   default because timelines matter for analysis — only `DOB` / birth-date
   columns and inline date *strings* are redacted. If your compliance review
   requires all dates removed, redact those columns manually or request a
   custom build.
3. Name detection now combines deterministic patterns (honorifics, "Last,
   First", initials, labeled roles) with **document-level entity memory**:
   once a name is seen, later variants ("Ms. Montoya", "A. Montoya",
   "Montoya") are flagged too. Unlabeled narrative names are caught via
   context, and OCR-corrupted spellings (J0hn, Mar-\ngaret) are handled by a
   normalization pass. Ambiguous tokens (May, Jordan, Brown) are only
   redacted when person-context or a prior mention supports it — they are
   not blind redactions. The **Extra literal texts** box remains the most
   reliable catch for known subjects; add every case subject's full name
   there.
4. Scanned/image-only PDFs have no text layer — detection finds nothing
   without OCR.  Enable the **OCR checkbox** to process these (requires
   a local Tesseract installation); see the OCR section below.
5. The bare 7–10 digit number pattern (unique IDs) may catch benign long
   numbers; disable `unique_ids` in a custom preset if that is too aggressive
   for your documents.

## OCR support (scanned & image-only documents)

When **Enable OCR** is checked (requires a local Tesseract installation),
the tool renders PDF pages to images, runs OCR with word-level bounding
boxes, and applies redactions using the same 19-category detection
pipeline. This covers:

- **Image-only / scanned PDFs** (the ones that show "0 detections" without
  OCR — treat that as a warning, not a pass).
- **Mixed PDFs** with native text on some pages and scanned content on
  others.
- **Standalone images**: PNG, JPEG, TIFF, BMP, WebP.

To use it:

1. [Install Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
   (free, offline).  Make sure `tesseract.exe` is on your PATH or set the
   `TESSERACT_CMD` environment variable.
2. Tick **Enable OCR** in the output options.
3. Scan and redact as usual — OCR detections are merged with text-based
   results. Image-only files are handled exclusively via OCR.

OCR is accurate for machine-printed text at reasonable resolution.
Handwriting, stylized fonts, and low-resolution scans will produce
low-confidence results surfaced as warnings.

## Verification & audit trail

- **Auto-verify**: after every redaction batch, each output file is
  re-scanned and reported as `PASS` (zero residual detections) or
  `NEEDS_REVIEW`. A standalone **Verify Last Batch** button re-runs this
  on demand.
- **Recoverability check (fail-closed)**: after export, the tool re-extracts
  every reachable representation — PDF text layer *and raw content streams*,
  link URIs, embedded files, form fields, DOCX/XLSX XML including footnotes,
  text boxes, comments, and app.xml — and confirms targeted identifiers
  cannot be recovered. If any survive, the result is marked `NEEDS_REVIEW`,
  never `PASS`. A missing/empty output is treated as an error.
- **Audit log**: each batch writes `redaction_log_<timestamp>.json` next
  to the outputs — source file, preset, per-category counts, verify
  result, and timestamp for every entry.
- **Redaction plans**: OCR-processed files also save a detailed
  `<name>_plan.json` with bounding boxes and masked previews.
- **Salted fingerprints**: plan fingerprints use a random per-batch salt
  (`hash_salt` in the log) — unsalted SHA-256 of short values like SSNs
  would be brute-forceable.

## Hidden-content coverage

Beyond visible text, the tool also scrubs:

| Container | Formats | Behavior |
|---|---|---|
| Link annotation URIs (`mailto:?ssn=…`) | PDF | Deleted when they trip the detector |
| Embedded file attachments | PDF | Removed when their content contains PII |
| AcroForm field values | PDF | Field deleted + area blacked out |
| Text boxes / shapes | DOCX | Masked via raw XML walk |
| Footnotes, endnotes, comments | DOCX | Masked via raw XML walk |
| Cell comments / notes | XLSX | Removed when they contain PII |
| Print headers / footers | XLSX | Cleared when they contain PII |
| `docProps/app.xml` Manager/Company | DOCX, XLSX | Blanket-cleared |
| Document metadata (author, etc.) | All | Blanket-cleared |

Optional **Presidio NER** (Microsoft, local in-process) can supplement
name detection in OCR pipelines: `pip install -r requirements-presidio-optional.txt`
then tick *Presidio NER*. The tool never starts a Presidio server and
works fully offline without it.

## Project layout

- `redaction_tool/ocr.py` — OCR engine (scan → plan → apply → verify)
- `redaction_tool/detector.py` — PII/PHI patterns, built-in presets, multi-pass `detect()`
- `redaction_tool/names.py` — high-recall name detection (honorifics, labels, compound surnames, initials)
- `redaction_tool/dates.py` — high-recall date/age detection (numeric, written, relative)
- `redaction_tool/ledger.py` — document-level entity memory (name-variant propagation)
- `redaction_tool/normalize.py` — NFKC / hyphen-join / OCR-tolerant normalization with offset mapping
- `redaction_tool/taxonomy.py` — canonical FERPA/HIPAA entity taxonomy + coverage map
- `redaction_tool/verify.py` — post-export recoverability (fail-closed)
- `redaction_tool/redactor.py` — per-format redaction engines + image output
- `redaction_tool/presets.py` — custom preset save/load/delete (JSON)
- `redaction_tool/gui.py` — Tkinter desktop app (drag & drop via tkinterdnd2)
- `run.py` — launcher with `--selftest`
- `references/` — methodology, plan schema, entity policy docs
- `templates/`, `examples/` — sample redaction plan files
- `SKILL.md` — Hermes/Bionic AI agent skill definition
- `tests/` — unit tests, high-recall tests, synthetic eval corpus + metrics
- `RedactionTool.spec` — PyInstaller one-file build config
- `Run-RedactionTool.bat` — double-click launcher (exe, or auto-installs
  deps and runs from source)
- `validate_real_files.py` — regression harness: redacts copies of real case
  files into a temp folder and verifies subject identifiers don't leak
- `.github/workflows/ci.yml` — CI: syntax check, unit tests, high-recall
  tests, synthetic evaluation, self-test
