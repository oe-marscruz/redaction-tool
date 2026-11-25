# Redaction Tool — FERPA / HIPAA

A local desktop tool that **permanently redacts** protected information from
**PDF, DOCX, and XLSX** documents. Everything runs on your machine — nothing
is uploaded anywhere, unlike Adobe Acrobat online services or ChatGPT.
Runs on **Windows 11 (and 10)** and **Linux**. Windows has a single-file
`.exe` and a per-user installer; Linux runs from source or from a single-file
binary (see [Quickstart](#quickstart)).
Includes **light and dark mode** (toggle in the top-right corner; your choice
is remembered between sessions in the per-user settings file — see
[Where your settings live](#where-your-settings-live)).

## Quickstart

### Windows 11

1. Download **`RedactionTool-Setup-<version>.exe`** from the
   [latest Release](https://github.com/oe-marscruz/redaction-tool/releases/latest)
   and double-click it — no admin password needed. Start it from the Start Menu.
2. Prefer no install? Download **`RedactionTool.exe`** and double-click it.

From a clone: double-click **`Run-RedactionTool.bat`** (creates a venv, installs
dependencies, launches the app).

### Linux

1. Install Python 3.10+ and Tesseract (needed only for OCR of scanned files):

   ```bash
   # Debian / Ubuntu
   sudo apt install python3 python3-venv python3-tk tesseract-ocr tesseract-ocr-eng
   # Fedora
   sudo dnf install python3 python3-tkinter tesseract tesseract-langpack-eng
   # Arch
   sudo pacman -S python tk tesseract tesseract-data-eng
   ```

2. Run the bundled launcher, which creates `.venv`, installs the pinned
   dependencies and starts the app:

   ```bash
   git clone https://github.com/oe-marscruz/redaction-tool
   cd redaction-tool
   ./Run-RedactionTool.sh
   ```

3. Optional — add a menu entry so the app shows up in your application list:

   ```bash
   ./Run-RedactionTool.sh --install-desktop-entry
   ```

Manual equivalent of the launcher:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run.py
```

Check the environment at any time (Tesseract, English data, Presidio, PyMuPDF):

```bash
.venv/bin/python tests/check_dependencies.py
```

**Linux packaging status:** the single-file binary is built and verified by
`./build_linux.sh` (see [BUILDING.md](BUILDING.md)); there is no distro package
or Flatpak yet, so the launcher or the venv install is the supported path.
Drag & drop needs a Tcl/Tk 8.x runtime (`tkinterdnd2`'s bundled `tkdnd`
does not load under Tcl/Tk 9); elsewhere the app still starts, with drag &
drop disabled and the file picker used instead.

## Where your settings live

| OS | Settings (`settings.json`) and custom presets (`presets/`) |
|---|---|
| Windows | `%USERPROFILE%\.redaction_tool\` (unchanged from earlier releases) |
| Linux | `$XDG_CONFIG_HOME/redaction-tool/` (default `~/.config/redaction-tool/`) |

On Linux, if `~/.redaction_tool/` already exists (an older source run) and the
XDG directory does not, the tool keeps using the old directory so presets are
never lost. Presets and settings survive upgrades and uninstalls on both OSes.

## What it detects

Detection categories are based on the
[18 HIPAA identifiers](https://cphs.berkeley.edu/hipaa/hipaa18.html) and
[FERPA-protected information](https://it.cornell.edu/ferpa-and-it/information-protected-ferpa):

| Category | HIPAA # | Notes |
|---|---|---|
| Names | 1 | Honorifics ("Dr. Jane Smith"), built-in list of 500+ common first names ("First Last", "Last, First", standalone first names), email-closing words excluded. |
| Addresses / ZIP / City, State | 2 | Street addresses (including apt/suite), PO boxes, city + state, ZIP+4, and 5-digit ZIPs in any position — labeled, after a state name, in a table cell, or standalone. |
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
| Financial info (FERPA/GLBA) | — | Tuition, aid, salary, etc. with $ amounts; payment card numbers (13–19 digits, Luhn-checked). |

**HIPAA #17 (full-face photos) cannot be auto-detected.** Review PDFs
manually; the tool leaves embedded images intact.

## Presets

- **FERPA Only** — student-focused categories.
- **HIPAA Only** — all 18 identifier categories.
- **Full (FERPA + HIPAA)** — everything.
- **Maximum / Strict** — every category, recall-first (highest false-positive
  tolerance, for cases where missing an identifier is worse than over-redacting).
- **Custom** — use *Customize / Save Preset…* to toggle categories and save
  your own profiles (stored in the per-user `presets` folder, see
  [Where your settings live](#where-your-settings-live)).

For known subjects (e.g. case respondents), paste their full names into the
**Extra literal texts** box — one per line. This is the most reliable way to
catch every occurrence, including nicknames. Advanced users can add regex
patterns, one per line.

**Adding many documents**: *Add Files…* takes a multi-selection, *Add
Folder…* queues every supported file in a folder and its subfolders
(PDF/DOCX/XLSX and images), and drag & drop works too. Article
`~$` lock files are skipped.

## Consistent pseudonym labels (qualitative coding)

Replacing everything with `[REDACTED]` protects a corpus but makes it hard to
follow one person or one account through a case file. Tick **Pseudonym
labels** to replace each detected value with a stable typed label instead:

```
before:  Alexandria Montoya (SSN 123-45-6789) called 303-555-0142.
after:   [NAME_1] ([SSN_1]) called [PHONE_1].
```

- The same value gets the same label for the whole batch (pass several case
  files in one run and `[NAME_1]` is the same person in each).
- Different values of a category get the next number (`[NAME_2]`,
  `[EMAIL_1]`, …), so coding can refer to "the subject" without the name.
- Labels are written into DOCX/XLSX text, PDF text, and OCR overlays. They
  are labels, not reversible tokens: **the value→label map exists only in
  memory and is never written to disk**, so a label cannot be turned back
  into the identifier. Keep your own mapping outside the redacted corpus if
  you need one.
- Category tags: `NAME, ADDRESS, DATE, PHONE, FAX, EMAIL, SSN, MRN,
  HEALTHPLAN, ACCOUNT, LICENSE, VEHICLE, DEVICE, URL, IP, BIOMETRIC, ID,
  STUDENTRECORD, FINANCIAL, CUSTOM`.
- Header-driven XLSX columns use the cell value itself, so repeated values in
  a roster share a label.
- OCR overlay boxes on standalone images stay opaque black (no label is drawn
  into pixels).

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

## Windows installer (details)

For most people — especially if you are not technical — use the installer:

1. Open the
   [latest Release page](https://github.com/oe-marscruz/redaction-tool/releases/latest)
   and download **`RedactionTool-Setup-<version>.exe`** (for example
   `RedactionTool-Setup-1.2.0.exe`).
2. Double-click it and follow the wizard. **No admin password is needed** — it
   installs just for your Windows account, into
   `C:\Users\<you>\AppData\Local\Programs\RedactionTool`.
3. Launch it from the Start Menu (there is an optional desktop-icon checkbox
   in the wizard).

What the installer takes care of for you:

- **Start Menu entry** ("Redaction Tool") and an optional desktop shortcut.
- **Uninstaller** appears in *Settings → Apps → Installed apps* (Apps &
  Features) as "Redaction Tool".
- **Older installed versions** are detected and upgraded automatically; a
  leftover portable `RedactionTool.exe` you downloaded earlier is offered for
  cleanup (default answer is *No* — it never deletes anything without asking,
  and never deletes an equal or newer copy).
- **Your presets and settings are preserved.** They live in
  `%USERPROFILE%\.redaction_tool\` and survive both upgrades and uninstalls.

> Note: the setup exe is a new artifact — it appears on the Release page from
> the first release that includes it onward. Until then, use the portable
> option below.

### Windows portable exe (no install)

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

If you cloned the repo and don't have the exe, use the bundled launcher — it
creates a venv and **auto-installs any missing dependencies** before launching:

- **Windows:** double-click **`Run-RedactionTool.bat`**
- **Linux:** run **`./Run-RedactionTool.sh`** (add `--install-desktop-entry` for
  a menu entry)

Manual equivalent (either OS — inside a clone):

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     Linux:  source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

### Building a binary

- **Windows** — fully bundled one-file `.exe` (Python, Presidio, spaCy model
  and Tesseract all inside), built with the staged runtime under
  `vendor\tesseract`; see [BUILDING.md](BUILDING.md). `tesseract-main.zip`
  contains source code only; the build never launches a Tesseract installer.

  ```powershell
  Set-ExecutionPolicy -Scope Process Bypass
  .\build_windows.ps1
  ```

- **Linux** — one-file binary with Python + Presidio + spaCy bundled. OCR uses
  the system `tesseract` unless you stage a runtime under `vendor/tesseract`;
  see [BUILDING.md](BUILDING.md).

  ```bash
  ./build_linux.sh
  ./dist/RedactionTool
  ```

> Note: single-file builds are occasionally flagged by antivirus heuristics
> (a known PyInstaller false positive). If that happens, build folder mode
> instead: `pyinstaller --noconfirm --onedir run.py`.

Run the headless self-test from source (works on both OSes, writes `OK`/`FAIL`
plus a per-format report):

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

When **Enable OCR** is checked (the packaged Windows release includes local
Tesseract and English data; on Linux and source runs the local installation is
used), the tool renders PDF pages to images, runs OCR with word-level bounding
boxes, and applies redactions using the same 19-category detection
pipeline. This covers:

- **Image-only / scanned PDFs** (the ones that show "0 detections" without
  OCR — treat that as a warning, not a pass).
- **Mixed PDFs** with native text on some pages and scanned content on
  others.
- **Standalone images**: PNG, JPEG, TIFF, BMP, WebP.

To use it:

1. Install Tesseract OCR and English trained data:
   - **Windows:** [UB-Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki);
     `tesseract.exe` on your PATH, or set `TESSERACT_CMD`. The release `.exe`
     bundles these.
   - **Linux:** your package manager
     (`sudo apt install tesseract-ocr tesseract-ocr-eng`,
     `sudo pacman -S tesseract tesseract-data-eng`). The tool finds
     `/usr/share/tessdata` and `/usr/share/tesseract-ocr/*/tessdata`; set
     `TESSERACT_CMD` or `TESSDATA_PREFIX` for unusual layouts.
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
  to the outputs — source file, preset, replacement mode, and for every
  document the per-category counts, the verify result, and an `audit` list of
  locations: which page / sheet cell / paragraph / header / footnote / form
  field was touched and with which categories. Structural labels only — no
  source text, no values.
- **Human-readable report**: the same batch also writes
  `redaction_report_<timestamp>.md` — a Markdown summary with document
  status (PASS / NEEDS_REVIEW), recoverability result, category totals, a
  "where" table per document, and a **Follow-up required** list for anything
  that failed. Safe to share when reviewing a redaction run: it contains no
  identifiers.
- **Redaction plans**: OCR-processed files also save a detailed
  `<name>_plan.json` with bounding boxes and masked previews.
- **Salted fingerprints**: plan fingerprints use a random per-batch salt
  (`hash_salt` in the log) — unsalted SHA-256 of short values like SSNs
  would be brute-forceable.
- **Corpus harness**: `python validate_real_files.py FILE ... --must-not-leak
  "Full Name"` redacts copies of the given files into a scratch directory and
  reports any surviving identifier. Point it at **synthetic** files during
  development and in CI; never commit real case files.

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

**Presidio NER** (Microsoft, local in-process) supplements name and location
detection for native PDF, DOCX, XLSX, and OCR text. It is enabled by default
when installed and can be unchecked in the UI. Install it for source runs with
`pip install -r requirements-presidio-optional.txt`; the Windows release build
bundles Presidio and its English model. The tool never starts a Presidio server.
The statistical model can produce false positives and false negatives; review
detections before redacting. Its output is subject to the same credibility
gate as the deterministic name detector, so model noise such as a ratio
(`Ratio 5/97`) or a header (`Email`) is not reported as a person.

**Detection quality.** The synthetic corpus (`tests/eval_corpus.py`, 334
documents / 345 gold spans) is scored by `python tests/eval_metrics.py`:
strict category-correct P/R/F1 `0.9971/1.0000/0.9986`, exact-span P/R
`0.8699/0.8725`, character coverage P/R `0.9646/0.9943`, and the
optional-Presidio A/B gate PASSes (recall unchanged, precision within its 2%
budget). These are synthetic fixtures, not production recall claims. The one
remaining false positive is the corpus's `Item catalog # 55432` line: a bare
5-digit token is always treated as a ZIP, because the alternative — requiring
a `ZIP` label or `City, ST` in front — leaked 173 real ZIPs from roster cells
and full-state-name addresses in an independent held-out evaluation. A
redacted catalog number is harmless; a redacted ZIP is not. Two behaviours
keep the counts honest and the redaction coverage identical:

- Overlapping detections of the *same* category (a name plus its possessive
  fragment, a PO box plus its ZIP) become one union span, so the same
  characters are not counted twice.
- A detection fully contained in another category's span (a phone number
  inside `Fax: …`, a name inside an email address) is reported once, under
  the containing category; explicit *Extra literal texts* are never dropped.

## Project layout

- `redaction_tool/ocr.py` — OCR engine (scan → plan → apply → verify), cross-platform Tesseract discovery
- `redaction_tool/detector.py` — PII/PHI patterns, built-in presets, multi-pass `detect()`
- `redaction_tool/names.py` — high-recall name detection (honorifics, labels, compound surnames, initials)
- `redaction_tool/dates.py` — high-recall date/age detection (numeric, written, relative)
- `redaction_tool/ledger.py` — document-level entity memory (name-variant propagation)
- `redaction_tool/normalize.py` — NFKC / hyphen-join / OCR-tolerant normalization with offset mapping
- `redaction_tool/taxonomy.py` — canonical FERPA/HIPAA entity taxonomy + coverage map
- `redaction_tool/verify.py` — post-export recoverability (fail-closed)
- `redaction_tool/audit.py` — per-location audit trail + Markdown batch report
- `redaction_tool/pseudonyms.py` — batch-scoped typed labels (`[NAME_1]`), in-memory only
- `redaction_tool/redactor.py` — per-format redaction engines + image output
- `redaction_tool/presets.py` — custom preset save/load/delete (JSON)
- `redaction_tool/paths.py` — per-user settings/preset location (Windows `%USERPROFILE%`, Linux XDG)
- `redaction_tool/gui.py` — Tkinter desktop app (drag & drop via tkinterdnd2, optional)
- `run.py` — launcher with `--selftest`
- `references/` — methodology, plan schema, entity policy docs
- `templates/`, `examples/` — sample redaction plan files
- `SKILL.md` — Hermes/Bionic AI agent skill definition
- `tests/` — unit tests, high-recall tests, platform tests, product-feature tests (`test_product_features.py`), GUI smoke test, synthetic eval corpus + metrics
- `RedactionTool.spec` — PyInstaller one-file build config (Windows and Linux)
- `Run-RedactionTool.bat` — Windows double-click launcher (exe, or auto-installs deps and runs from source)
- `Run-RedactionTool.sh` — Linux launcher (exe, or venv + deps from source); `--install-desktop-entry` adds a menu entry
- `build_windows.ps1` / `build_linux.sh` — reproducible single-file builds (see [BUILDING.md](BUILDING.md))
- `validate_real_files.py` — corpus harness: redacts copies of the given files into a temp folder and verifies subject identifiers don't leak
- `.github/workflows/ci.yml` — CI on `windows-latest` **and** `ubuntu-latest`: scope gate, syntax check,
  unit/high-recall/security/platform tests, GUI smoke test (headless X), synthetic evaluation, self-test,
  plus real-binary build jobs for both OSes
