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

## Quick start

Double-click **`Run-RedactionTool.bat`** — it launches the included standalone
exe, or auto-installs Python dependencies if running from source.

## Standalone executable (recommended)

`dist\RedactionTool.exe` is a **fully self-contained single-file build** —
the Python runtime and every dependency (PyMuPDF, python-docx, openpyxl,
tkinterdnd2) are bundled inside it. The host computer needs **nothing
installed**: no Python, no packages, no network access. Just copy the exe
anywhere and double-click it. This is the safest option for sensitive data
because the tool never touches the network.

If the exe is not included in your download (e.g. a git clone), rebuild it:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm RedactionTool.spec
```

Validate the packaged exe on any machine (headless, writes `OK`/`FAIL`):

```
RedactionTool.exe --selftest result.txt
```

Rebuild it yourself after changing the code:

```bash
cd RedactionTool
.venv\Scripts\activate
pip install pyinstaller
pyinstaller --noconfirm RedactionTool.spec
```

> Note: single-file exe builds are occasionally flagged by antivirus
> heuristics (a known PyInstaller false positive). If that happens, build
> folder mode instead: `pyinstaller --noconfirm --onedir run.py`.

## Run from source

Double-click **`Run-RedactionTool.bat`** — it launches the exe when present,
or otherwise creates a venv and **auto-installs any missing dependencies**
before starting the app. Manual equivalent:

```bash
cd RedactionTool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Validate (headless self-test, from source)

```bash
python run.py --selftest result.txt
```

Builds sample PDF/DOCX/XLSX files containing known PII, redacts them, and
verifies nothing leaks. Writes `OK` or `FAIL` plus a per-format report to
`result.txt`.

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
3. Name detection is tuned to avoid redacting common English words (months,
   verbs). Standalone first names are caught only when capitalized and
   unambiguous — surnames alone ("Drollinger") and uncommon first names need
   the **Extra literal texts** box. Always add each case subject's full name
   there.
4. Scanned/image-only PDFs have no text layer — detection will find nothing.
   Such documents need OCR first (not included). The scan step will show
   zero detections for these files — treat that as a warning, not a pass.
5. The bare 7–10 digit number pattern (unique IDs) may catch benign long
   numbers; disable `unique_ids` in a custom preset if that is too aggressive
   for your documents.

## Project layout

- `redaction_tool/detector.py` — PII/PHI patterns, built-in presets, `detect()`
- `redaction_tool/redactor.py` — per-format redaction engines + image output
- `redaction_tool/presets.py` — custom preset save/load/delete (JSON)
- `redaction_tool/gui.py` — Tkinter desktop app (drag & drop via tkinterdnd2)
- `run.py` — launcher with `--selftest`
- `RedactionTool.spec` — PyInstaller one-file build config
- `Run-RedactionTool.bat` — double-click launcher (exe, or auto-installs
  deps and runs from source)
- `dist/RedactionTool.exe` — the built standalone executable
- `validate_real_files.py` — regression harness: redacts copies of real case
  files into a temp folder and verifies subject identifiers don't leak
