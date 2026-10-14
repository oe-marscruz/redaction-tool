# Presidio Integration Baseline & Safety Inventory

## Baseline Metadata
- **Commit SHA**: `6d7976737da16fa3bdb067a334cd02b107d85c0d`
- **Audit Date**: 2026-03-31
- **Scope**: Baseline evaluation of current `redaction-tool` codebase, test suite, and optional Presidio integration boundary.

---

## File & Function Integration Map

### 1. `redaction_tool/detector.py`
- **`Match`**: Dataclass representing a detection item (`text`, `category`, `start`, `end`, `entity_type`, `confidence`, `evidence`).
- **`CATEGORIES` & `CATEGORY_MAP`**: Defines the 19 standard categories across HIPAA and FERPA taxonomy.
- **`PRESETS`**: Prebuilt profiles ("FERPA Only", "HIPAA Only", "Full (FERPA + HIPAA)", "Maximum / Strict").
- **`_PRESIDIO_ENTITY_MAP`**: Current mapping table:
  - `PERSON` -> `names`
  - `LOCATION` -> `addresses`
- **`_presidio_model_path()`**: Locates local `en_core_web_sm-3.8.0` model package directory in source or PyInstaller bundle (`_MEIPASS`).
- **`presidio_is_available()`**: Returns `True` iff `presidio_analyzer`, `spacy`, and model path are importable/available.
- **`get_presidio_engine()`**: Returns cached local `AnalyzerEngine` using local `NlpEngineProvider` and `RecognizerRegistry` (with `SpacyRecognizer` for `en`). Configures offline `tldextract`.
- **`_presidio_matches(text, enabled, context)`**: Invokes `AnalyzerEngine.analyze(text=text, entities=..., language="en")` filtered by active `enabled` categories. Discards results scoring below `_PRESIDIO_MIN_SCORE` (0.65), because Presidio's pattern and checksum recognizers otherwise emit bare digit runs and dates as low-confidence SSNs, bank numbers, driver licenses, and phone numbers that the deterministic passes already cover more accurately; admitting them added ~63 false positives to the synthetic corpus with no recall gain. Remaining scores convert to confidence (`CONFIRMED` if >= 0.85, else `LIKELY`). Raises `RuntimeError` if analysis fails (fail-closed).
- **`detect(text, enabled_categories, custom_patterns, custom_texts, use_presidio)`**: Executes 7-pass pipeline:
  - Pass 0: Normalization & offset indexing (`_normalize.build_normalized`)
  - Pass 1: Structured regex on original & normalized text
  - Pass 2: High-recall name & date detectors
  - Pass 3: In-memory document entity ledger (`_ledger.EntityLedger`)
  - Pass 4: Custom regex & literal matches
  - Pass 5: Optional local Presidio NLP supplement (`use_presidio=True`)
  - Pass 6: Span deduplication (`_dedupe`)
- **`_dedupe(matches)`**: Overlap union where longest span wins; merges confidence and evidence.

### 2. `redaction_tool/ledger.py`
- **`EntityLedger`**: Process-local, per-detection-call name memory. Ingests confirmed name tokens (Pass 1 & Pass 2 hits) and propagates variations (first name, surname, initial + surname, honorifics, OCR variants).
- **Note**: Ingests names *before* Pass 5 (Presidio) runs.

### 3. `redaction_tool/taxonomy.py`
- Canonical FERPA PII (34 CFR § 99.3) and HIPAA Safe Harbor (45 CFR § 164.514(b)(2)) taxonomy keys.
- **`CATEGORY_TO_ENTITY`**: Maps category keys to taxonomy constants (`PERSON_NAME`, `ADDRESS`, `SSN`, etc.).
- **`PolicyProfile` & `PROFILES`**: Regulatory profiles (`general`, `ferpa`, `hipaa`, `strict`).
- **`HIPAA_COVERAGE` & `FERPA_COVERAGE`**: Documented category coverage breakdown.

### 4. `redaction_tool/presets.py`
- Preset disk management (`builtin_presets`, `save_preset`, `load_presets`, `delete_preset`, `list_all_presets`).

### 5. `redaction_tool/redactor.py`
- **`ScanOptions`**: Configuration dataclass (`enabled_categories`, `custom_patterns`, `custom_texts`, `replacement`, `hash_salt`, `use_presidio`).
- **`_redact_pdf()`**: PyMuPDF redaction annotations, widget/link/attachment scrubbing, XML metadata deletion.
- **`_redact_docx()`**: Paragraph, table, header, footer masking, `_redact_docx_hidden_parts()` for textboxes/footnotes/endnotes/comments, and `_scrub_opc_app_xml()` for Manager/Company fields.
- **`_process_xlsx()` / `_redact_xlsx()`**: Openpyxl cell iteration, header-mapped PII column matching (`_HEADER_MAP` -> `_header_columns`), cell comments, and print header/footer scrubbing.
- **`redact_file()`**: Unified entry point returning `RedactResult`.
- **`iter_text_units()`**: Extracts text per processing unit matching redactor granularity.

### 6. `redaction_tool/ocr.py`
- Local Tesseract OCR wrapper (`find_tesseract`, `find_tessdata`, `run_ocr`, `OCRWord`).
- **`detect_on_ocr()`**: Runs `detect()` on OCR text stream, calculates pixel bboxes, generates masked previews and salted SHA-256 fingerprints.
- **`scan_ocr_pdf()`, `scan_ocr_image()`, `apply_ocr_redactions()`, `verify_ocr()`**: Plan generation, application, and re-scan verification.

### 7. `redaction_tool/verify.py`
- Post-export fail-closed recoverability verification (`recoverable_text`, `values_still_present`, `verify_export`). Ensures targeted values (>= 4 chars) are unrecoverable from raw streams/ZIP XML.

### 8. `redaction_tool/gui.py`
- Tkinter GUI application (`App`, `_scan_options`, `_batch_worker`, `_scan_worker`, `_redact_worker`, `_verify_worker`).
- Presidio UI toggle (`presidio_var`, `presidio_cb`).
- PDF OCR overlay logging in `_redact_worker` (line 927: `lines.append(f"  OCR pass skipped — {exc}")`).

---

## Confirmed API Whitelist & Entity Mapping Candidates

### Baseline Mapping (`detector._PRESIDIO_ENTITY_MAP`)
- `"PERSON"` -> `"names"`
- `"LOCATION"` -> `"addresses"`

### Presidio API Inspection Status
- **Environment Status**: `presidio-analyzer` and `spacy` packages are currently **not installed** in the active local Python environment.
- **Source Checkout Status**: No local `presidio-main` source directory exists in the workspace.
- **Prerequisite Prerequisite Alert**: Because neither the installed `presidio-analyzer` package nor a local `presidio-main` checkout is present, executing runtime inspection of `RecognizerRegistry.load_predefined_recognizers()` is **BLOCKED**.

### Standard Presidio Predefined Recognizers (Reference Registry Inventory)
When `presidio-analyzer` 2.2.364 is installed, the predefined recognizer registry supports the following entity types:
- `PERSON` (maps to `names`)
- `LOCATION` (maps to `addresses`)
- `EMAIL_ADDRESS` (candidate maps to `emails`)
- `PHONE_NUMBER` (candidate maps to `phones`)
- `US_SSN` (candidate maps to `ssn`)
- `US_BANK_NUMBER`, `IBAN_CODE`, `CREDIT_CARD` (candidate maps to `accounts` / `financial`)
- `US_DRIVER_LICENSE` (candidate maps to `licenses`)
- `US_PASSPORT`, `US_ITIN` (candidate maps to `unique_ids` / `licenses`)
- `IP_ADDRESS` (candidate maps to `ips`)
- `URL` (candidate maps to `urls`)
- `DATE_TIME` (candidate maps to `dates`)
- `MEDICAL_LICENSE` (candidate maps to `licenses`)

*Note*: Any expansion of `_PRESIDIO_ENTITY_MAP` beyond `PERSON` and `LOCATION` must remain BLOCKED until the pinned `presidio-analyzer` package or local source is present and verified.

---

## Prior Failure Risks & Expected Safety Checks

1. **Unconstrained NLP Over-Redaction**:
   - *Risk*: Presidio entities returning matches for categories disabled in the GUI profile.
   - *Check*: `_presidio_matches()` must continue filtering matches against `enabled` categories (`if category in enabled`).
2. **Fail-Open Exception Suppression**:
   - *Risk*: Suppressing NLP exceptions during `analyze()` could result in silently missing PII.
   - *Check*: `_presidio_matches()` raises `RuntimeError` on analysis failure (tested by `test_presidio_fails_closed_when_analysis_errors`).
3. **Entity Ledger Execution Order**:
   - *Risk*: Ingesting names into `EntityLedger` before Presidio runs might miss Presidio-only discovered names for document-wide variant propagation.
   - *Check*: Inspect whether Pass 3 ledger propagation should run before, after, or iteratively with Pass 5 Presidio without introducing infinite loops or performance degradation.
4. **XLSX Empty vs None Category Handling**:
   - *Risk*: `enabled_categories=None` (means default/all) vs `enabled_categories=[]` (means no standard categories).
   - *Check*: Ensure XLSX header matching (`_header_columns`) correctly distinguishes `None` from `[]`.
5. **GUI PDF OCR Overlay Error Visibility**:
   - *Risk*: OCR failure during PDF overlay pass being silently swallowed.
   - *Check*: `gui.py` logs `OCR pass skipped — {exc}` in batch results.
6. **Data Leakage via Hidden Streams & Metadata**:
   - *Risk*: PII remaining in PDF widgets, link URIs, attachments, DOCX textboxes, footnotes, comments, or `docProps/app.xml`.
   - *Check*: Post-export verification (`verify_export`) verifies 0 recoverable targeted values (>= 4 chars).

---

## Per-Test Baseline Outcomes

| Command | Status | Details / Summary |
| :--- | :--- | :--- |
| `python tests/test_core.py` | **PASS** | 18 test functions executed. 1 skipped internally (`test_presidio_actual_name_and_location_detection_offline`) due to uninstalled optional Presidio package. Overall suite: ALL PASS. |
| `python tests/test_high_recall.py` | **PASS** | 27 test functions executed. Overall suite: ALL PASS. |
| `python tests/eval_metrics.py` | **PASS** | 315 synthetic docs, 331 gold entities. P=1.0000, R=1.0000, F1=1.0000, FN=0, FP=0. |
| `python run.py --selftest result.txt` | **PASS** | Generated sample DOCX, XLSX, PDF files. Redacted 5 items per document. 1 image page rendered. Self-test passed cleanly. |
| `python -m compileall -q redaction_tool tests` | **PASS** | Compiled all module source files with zero syntax errors. |
| `python tests/check_dependencies.py` | **BLOCKED (Environment)** | Tesseract, PyMuPDF, Pillow available (`ready_for_images`: true, `ready_for_pdfs`: true). Presidio/spaCy dependencies not installed (`ready_for_presidio`: false). |

---

## Required Acceptance Checks for Phases 2–5

- **Phase 2 (Invariants & Core Behavior)**:
  - Verify `use_presidio=False` yields identical detection results across all formats.
  - Verify `enabled_categories=None` defaults to all categories while `enabled_categories=[]` disables standard categories while respecting custom patterns/literals.
  - Audit XLSX empty/header category handling.
- **Phase 3 (Presidio Integration Boundary & Mapping)**:
  - If optional Presidio dependencies are installed, verify entity mapping candidates against `RecognizerRegistry`.
  - Validate fail-closed behavior on Presidio error across all pipeline entries.
  - Ensure Presidio predictions never exceed active GUI/profile category selection.
- **Phase 4 (Document Engine & Recoverability)**:
  - Test PDF, DOCX, XLSX, and Image redactions against hidden elements (widgets, URIs, attachments, textboxes, footnotes, comments, `app.xml`).
  - Run `verify_export()` on all outputs.
- **Phase 5 (End-to-End Verification & Final Handoff)**:
  - Execute full test suite, headless selftest, compileall, and evaluation metrics.
  - Confirm zero PII leakage in CI/test logs and zero file modification outside allowlist.

---

## System & Regulatory Limitations

1. **Full-Face Photographs & Biometrics**:
   - HIPAA Safe Harbor Identifier #17 (full-face photos) and handwritten PII are **NOT** auto-detected by text, OCR, or NER engines.
   - Manual review is strictly required for image/photo content in documents.
2. **Non-Certification Notice**:
   - Software execution and automated redaction do not constitute a legal or regulatory certification of HIPAA or FERPA compliance.
   - Human review remains mandatory for legal compliance determinations.
3. **Recall Guarantee**:
   - Perfect recall is not claimed or guaranteed.
4. **Presidio Precision Floor**:
   - Presidio results scoring below `_PRESIDIO_MIN_SCORE` (0.65) are discarded. On the
     synthetic corpus every such result was a low-confidence pattern-recognizer
     misfire (bare digit runs reported as SSNs, bank numbers, or driver licenses;
     dates reported as phone numbers), and discarding them removed 40 false
     positives with no change in recall (0.9942 both with and without the floor).
   - The only gold entity in the corpus recovered solely by Presidio is a
     well-formed credit card scoring 1.00, so the floor does not suppress it.
   - `tests/eval_metrics.py` gates this: the `ab_comparison.status` field is
     computed, not hardcoded, and is `FAIL` if Presidio drops recall at all
     (`AB_MAX_RECALL_DROP`) or precision by more than `AB_MAX_PRECISION_DROP`.
