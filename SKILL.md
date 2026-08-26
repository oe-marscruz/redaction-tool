---
name: ocr-redaction-local
description: Locally detect and redact sensitive text in images and PDFs
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [privacy, ocr, redaction, pdf, images, pii, local]
    category: productivity
    requires_toolsets: [terminal]
    config:
      - key: ocr_redaction.tesseract_cmd
        description: Path or command name for the local Tesseract executable
        default: tesseract
        prompt: Tesseract executable path or command name
      - key: ocr_redaction.default_dpi
        description: DPI used when rendering PDF pages for OCR
        default: "200"
        prompt: Default OCR render DPI
---
# OCR Redaction Local

## When to Use

Use this skill when the user needs sensitive information permanently redacted from:

- scanned or image-only PDFs;
- mixed PDFs containing native text plus screenshots, scans, signatures, or embedded images;
- PNG, JPEG, TIFF, BMP, or WebP images containing text;
- documents where ordinary text extraction is not sufficient because sensitive text may exist only as pixels.

Use a normal text/document redaction workflow instead when the source contains only plain text and no rasterized content.

This is a **local-only application workflow**. Do not use MCP, HTTP services, cloud OCR, cloud PII APIs, remote vision APIs, or persistent listeners as part of this skill.

## Procedure

1. **Preserve the source.** Never overwrite the original. Work from a copy or write to a new output path.
2. **Check local dependencies.** Run:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/check_dependencies.py"
   ```

   Required for PDF work: Python 3, PyMuPDF, Pillow, and a local Tesseract executable. Presidio is optional and expands named-entity detection.
3. **Create a redaction plan before applying changes.** For a PDF:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/ocr_redact.py" scan input.pdf \
     --output plan.json --dpi 200
   ```

   For an image:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/ocr_redact.py" scan input.png \
     --output plan.json
   ```

4. **Review the plan.** The default plan stores bounding boxes, entity types, confidence, masked previews, and SHA-256 fingerprints — not full detected sensitive values. Inspect `detections`, `warnings`, and low-confidence entries before continuing.
5. **Add or remove detections if necessary.** Manual redaction boxes may be added to the plan using the schema in `references/plan-schema.md`. When compliance or policy requires specific identifiers, load `references/entity-policy.md` before editing the plan.
6. **Apply the approved plan.** For PDF input:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/ocr_redact.py" apply input.pdf \
     --plan plan.json --output input.redacted.pdf
   ```

   For images:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/ocr_redact.py" apply input.png \
     --plan plan.json --output input.redacted.png
   ```

   PDF redactions must use true PDF redaction annotations and `apply_redactions`; do not merely draw opaque rectangles over content.
7. **Verify after redaction.** Run:

   ```bash
   python "${HERMES_SKILL_DIR}/scripts/ocr_redact.py" verify input.redacted.pdf \
     --report verification.json --dpi 200
   ```

   Verification re-runs OCR/PII detection against the resulting file and reports any remaining detectable sensitive entities. Treat a non-empty result as `NEEDS_REVIEW`, not as success.
8. **Report limitations clearly.** OCR can miss handwriting, low-resolution text, stylized fonts, rotated text, obscured text, or unsupported languages. A passing automated verification is not a legal or regulatory compliance guarantee.

### Detection policy

Default deterministic recognizers cover common structured identifiers such as email addresses, US SSNs, phone-like numbers, credit-card candidates with Luhn validation, IP addresses, and URLs. Optional Microsoft Presidio integration can add named entities such as people and locations when installed locally.

Do not claim a named person was detected unless the recognizer actually returned that span. Do not invent sensitive values.

### Coordinate policy

For OCR-derived detections, preserve the OCR bounding box. For PDFs, convert the rendered-image pixel rectangle back to PDF page coordinates before writing the plan. This lets the same mechanism redact text appearing inside scanned pages and embedded screenshots/images.

### Local-only contract

- No MCP servers.
- No listening ports or background daemons.
- No external OCR APIs.
- No external PII APIs.
- No remote model is required for detection or redaction.
- Do not upload source documents or extracted sensitive values.
- Do not install dependencies automatically without the user's approval.
- Keep the source unchanged and create a new redacted output.
- Store full detected sensitive values in the plan only when the user explicitly requests that behavior.

## Pitfalls

- A black rectangle drawn on top of text is not necessarily a true redaction. For PDFs use PyMuPDF redaction annotations followed by `apply_redactions()`.
- OCR text coordinates are measured in rendered-image pixels; PDF redaction coordinates are page points. Never use OCR pixel boxes directly on a PDF.
- Image-only PDF text will not appear in ordinary PDF text extraction. OCR the rendered page.
- Native PDF text can render differently from OCR. Use the OCR geometry for raster-sensitive detection and true PDF redaction for removal.
- Low OCR confidence can produce false positives and false negatives. Do not silently discard low-confidence candidate regions; surface them for review.
- Presidio's Analyzer can run locally as Python code. Do not start its HTTP service for this skill.
- Do not use the output as evidence of HIPAA, GDPR, PCI DSS, FERPA, GLBA, or other regulatory compliance without a separately defined policy profile and human/legal review.
- Signatures, faces, photographs, barcodes, QR codes, and non-text visual identifiers require separate detectors or manual boxes; OCR alone is not sufficient.

## Verification

A successful run must satisfy all of the following:

1. Original source file still exists and was not modified.
2. Output file opens successfully.
3. Every planned PDF redaction was applied, not merely annotated.
4. Raster output contains opaque replacement pixels over approved boxes.
5. Post-redaction OCR/PII scan completed.
6. Verification report contains zero remaining high-confidence entities, or the result is explicitly marked `NEEDS_REVIEW`.
7. Any low-confidence OCR areas, unsupported pages, or parsing failures are reported.
8. No network service or remote API was required by the bundled scripts.

For higher-assurance use, manually inspect rendered output pages in addition to automated verification.
