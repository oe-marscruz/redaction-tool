#!/usr/bin/env python3
import importlib.util, json, shutil, sys

def present_module(name):
    return importlib.util.find_spec(name) is not None

report = {
    "python": sys.version.split()[0],
    "tesseract": shutil.which("tesseract"),
    "pymupdf": present_module("pymupdf") or present_module("fitz"),
    "pillow": present_module("PIL"),
    "presidio_analyzer_optional": present_module("presidio_analyzer"),
}
report["ready_for_images"] = bool(report["tesseract"] and report["pillow"])
report["ready_for_pdfs"] = bool(report["tesseract"] and report["pillow"] and report["pymupdf"])
print(json.dumps(report, indent=2))
if not report["ready_for_images"]:
    sys.exit(2)
