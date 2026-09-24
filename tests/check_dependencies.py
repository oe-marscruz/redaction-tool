#!/usr/bin/env python3
import importlib.util, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def present_module(name):
    return importlib.util.find_spec(name) is not None

try:
    from redaction_tool import ocr as ocr_support
    bundled_tesseract = ocr_support.find_tesseract()
    bundled_tessdata = ocr_support.find_tessdata()
except Exception:
    bundled_tesseract = None
    bundled_tessdata = None

report = {
    "python": sys.version.split()[0],
    "tesseract": bundled_tesseract or shutil.which("tesseract"),
    "pymupdf": present_module("pymupdf") or present_module("fitz"),
    "pillow": present_module("PIL"),
    "presidio_analyzer_optional": present_module("presidio_analyzer"),
    "spacy_optional": present_module("spacy"),
    "spacy_english_model_optional": present_module("en_core_web_sm"),
}
report["english_traineddata"] = bool(bundled_tessdata)
report["ready_for_presidio"] = bool(
    report["presidio_analyzer_optional"]
    and report["spacy_optional"]
    and report["spacy_english_model_optional"]
)
report["ready_for_images"] = bool(
    report["tesseract"] and report["english_traineddata"] and report["pillow"]
)
report["ready_for_pdfs"] = bool(
    report["ready_for_images"] and report["pymupdf"]
)
print(json.dumps(report, indent=2))
if not report["ready_for_images"]:
    sys.exit(2)
