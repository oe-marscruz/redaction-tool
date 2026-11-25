# redaction-product lane — audit, comparison, plan

Branch: `swarm/product`. Scope: detection/redaction quality, UX, verification reports.
Not in scope (lane `redaction-platform`): CI, launchers, build scripts, installer, Linux/Windows install docs.

## 1. Audit (Linux, Python 3.13.14 venv via `uv venv -p 3.13`)

Baseline commands and results (full output in the final report):

| Command | Result |
|---|---|
| `python tests/test_core.py` | FAIL — 1 case (`test_image_round_trip`) because `find_tessdata()` only probes bundled/Windows paths; Arch/Debian store data in `/usr/share/tessdata`. Passes with `TESSDATA_PREFIX=/usr/share/tessdata`. Platform-lane concern. |
| `python tests/test_high_recall.py` | ALL PASS |
| `python tests/test_presidio_integration.py` | ALL PASS |
| `python -m unittest tests/test_document_context.py` | 14 tests OK |
| `python -m unittest tests/test_security_verification.py` | 15 tests OK |
| `python -m unittest tests/test_end_to_end_presidio.py` | 5 tests OK |
| `python tests/eval_metrics.py` | strict P=0.9475 R=0.9942 F1=0.9703 FN=2 FP=19; A/B PASS |
| `python run.py --selftest` | OK |

### Detector error analysis (synthetic corpus, baseline, Presidio on)

19 strict false positives, 2 false negatives. Causes found by dumping per-document predictions:

1. **Overlapping same-category fragments** count as separate false positives and redact the same
   characters twice: `Saanvi Reddy` + `Reddy's`; `QUINN, HARPER` + `HARPER J`; `P.O. Box 44551` +
   `44551`. `_dedupe()` only compares with the previous surviving span and only drops *fully*
   contained same-category spans.
2. **Nested cross-category duplicates**: `Fax: 303-555-0188` (fax) + `303-555-0188` (phones);
   `Account Number 99887766` (accounts) + `99887766` (unique_ids); address `Denver, CO` + name
   `Denver`; email `alexandria.montoya@campus.edu` + names `alexandria`, `montoya`. All duplicates
   describe already-covered characters.
3. **Document-label bigrams read as names**: `US Passport No`, `Taxpayer ITIN`.
4. **Honorific run-on**: `Ms. Montoya and` — lowercase honorific branch swallows the conjunction, and
   the conjunction then seeds the ledger as a "name" (`and`).
5. **Bare 5-digit numbers are treated as ZIPs** unconditionally (`Item catalog # 55432` → address).
6. **Spaced payment-card numbers are not detected at all** (`4532 0151 1283 0366`, HIPAA #10 style
   financial identifier) — recall gap, no checksum use anywhere.

### Workflow gaps (user-facing)

- **Audit log has no locations.** `redaction_log_*.json` stores per-category counts only. The stated
  use case (large qualitative analysis of case files) needs "which page / sheet / cell / paragraph
  contained what category" for spot-checking, and the current log cannot support that. No
  human-readable report is produced.
- **Replacement is one constant string.** For qualitative coding, consistent pseudonyms
  (`[NAME_1]` for the same person across a case file and across a batch) are what keeps a coded
  corpus readable. Neither the GUI nor `ScanOptions` offers it.
- **Folder-level intake is missing.** Only multi-select and drag & drop; a case-file folder has to be
  expanded by hand.

## 2. Comparison (open-source projects)

| Project | URL | What it does well | Taken / rejected |
|---|---|---|---|
| Microsoft Presidio | https://github.com/microsoft/presidio (moved to https://github.com/data-privacy-stack/presidio) | Analyzer/anonymizer split; per-entity operators (replace, redact, mask, hash, encrypt); checksum-backed recognizers; benchmarks over a labelled corpus | **Taken:** checksum validation for payment cards (Luhn) so a 16-digit run is not a blind hit; already integrated as optional supplement. **Rejected:** its operator zoo and reversible encryption — this tool's contract is permanent removal, and adding reversible paths would weaken it. |
| Phileas (Philterd) | https://github.com/philterd/phileas | Policy-driven per-type transformation; **context-scoped consistent replacement** ("the same value is redacted the same way within one context"); validators (`luhn`, `mod11`); `redactionFormat` with `%t` for the type tag | **Taken:** consistent per-batch pseudonyms and typed label format. **Rejected:** Java policy DSL, realistic surrogate generation (fabricating names in a Title IX case file would create false facts). |
| pdf-redact | https://github.com/PickeledMonkey/pdf-redact | Review findings before export (selected/unselected); JSON audit report with counts and **masked** samples; batch CLI; ZIP rule **off by default as noisy** | **Taken:** masked-only audit trail and location detail; ZIP context gating. **Rejected:** interactive per-span selection (large Tk app change, high risk) — scan preview already gives counts per category. |
| scrubadub | https://github.com/LeapBeyond/scrubadub | Typed replacement tags (`{{EMAIL}}`), detector/post-processor separation, locale-aware addressing | **Taken:** typed, stable labels. **Rejected:** replacing its detectors — regex + optional Presidio is already stronger for FERPA/HIPAA labels. |
| Philter (UCSF lineage, BCHSI/philter-ucsf) | https://github.com/BCHSI/philter-ucsf | Clinical de-identification with surrogate generation, whitelists, `--verbose` audit output | **Taken:** whitelist/context discipline idea already present in ledger. **Rejected:** surrogate generation, as above. |

## 3. Ranked improvements (impact × effort)

1. **Detection dedupe/containment rewrite** (high impact, low effort) — union overlapping
   same-category fragments, drop fully contained cross-category duplicates, trim label bigrams and
   conjunctions, context-gate bare ZIPs, add Luhn-checked payment cards. Directly measurable on
   `tests/eval_metrics.py`.
2. **Consistent pseudonym mode** (high impact for the stated qualitative-coding workflow, medium
   effort) — `[NAME_1]`/`[EMAIL_2]` labels, stable per batch, written into DOCX/XLSX/PDF text, never
   persisted as a value→label map (the map would be PII).
3. **Audit locations + human-readable report** (high impact for compliance review, medium effort) —
   per page/sheet-cell/paragraph counts in the JSON log, plus `redaction_report_<stamp>.md` with
   counts and verify status, no plaintext.
4. **Folder intake in the GUI** (medium impact, small effort) — recursive add of supported types.
5. Rejected for this pass: interactive span review (needs a canvas renderer per format), reversible
   encryption, realistic surrogates, new dependencies.

## 4. Chosen scope

Items 1–4. Tests: `tests/test_product_features.py` (synthetic fixtures only). No changes to
`requirements*.txt`, CI files, launchers, or build/install docs.

## 5. Delivered

| Change | Files |
|---|---|
| Same-category overlap union + contained-span dedupe (coverage-preserving) | `redaction_tool/detector.py` (`_dedupe`), `redaction_tool/redactor.py` (cell dedupe call) |
| Name/date stopwords for conjunctions and identifier labels; quoted-alias surname; street address unit with comma | `redaction_tool/names.py`, `redaction_tool/detector.py` |
| Bare ZIP requires ZIP context; payment-card PANs with Luhn | `redaction_tool/detector.py` |
| Presidio PERSON/LOCATION credibility gate | `redaction_tool/detector.py` (`_presidio_matches`) |
| Batch-scoped pseudonym labels in DOCX/XLSX/PDF/OCR overlay | `redaction_tool/pseudonyms.py`, `redactor.py`, `ocr.py`, `gui.py` |
| Per-location audit + Markdown report, no plaintext | `redaction_tool/audit.py`, `redactor.py`, `gui.py` |
| Folder intake in GUI | `redaction_tool/gui.py` |
| Tests | `tests/test_product_features.py` (18 cases) |

Metrics (Presidio run / baseline identical strict scores):

| Metric | Before | After |
|---|---|---|
| Strict P/R/F1 | 0.9475 / 0.9942 / 0.9703 | 1.0000 / 1.0000 / 1.0000 |
| Exact span P/R | 0.8287 / 0.8696 | 0.8725 / 0.8725 |
| Char coverage P/R | 0.9554 / 0.9874 | 0.9656 / 0.9943 |
| FN / FP | 2 / 19 | 0 / 0 |
| Presidio A/B | PASS (recall equal, precision −0.0057) | PASS |

Synthetic-corpus score is not a production claim; corpus is 334 docs / 345 gold spans.
