# Building the single-file Windows executable

The release build is a **64-bit Windows one-file executable**. It bundles the
Python runtime, Presidio Analyzer, spaCy's English small model, Tesseract, and
English OCR trained data. The executable does not download any models or send
document text to a service.

## Prerequisites

- 64-bit Windows and CPython 3.13.
- The Tesseract source archive (`tesseract-main.zip`) is not a binary
  distribution. This build uses the staged Windows x64 runtime in
  `vendor\tesseract` and will not launch any installer. Ensure it contains
  `tesseract.exe`, its required `.dll` files, English trained data, and the TSV
  config file. Never point `-TesseractDir` at the source ZIP.
- Keep third-party binaries out of version control unless their redistribution
  terms and notices have been reviewed.

Example folder layout:

```text
vendor/
  tesseract/                 # staged from Windows Tesseract install
    tesseract.exe
    *.dll
    tessdata/
      eng.traineddata
      configs/
        tsv
  en_core_web_sm/
    meta.json
    en_core_web_sm-3.8.0/
      config.cfg
```

The spaCy model wheel is published in the
[Explosion spaCy models release](https://github.com/explosion/spacy-models/releases/tag/en_core_web_sm-3.8.0).
Its pinned version is compatible with spaCy 3.8. The English model is a
statistical NER model; it supplements the existing deterministic detector and
does not guarantee detection of all PII.

## Build

From PowerShell at the repository root (internet is needed on the build
machine to download Python packages and the pinned spaCy model wheel; the
resulting executable is designed to work offline):

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

The script installs pinned dependencies into `.venv`, downloads and verifies
the spaCy model, stages it for PyInstaller, validates the staged Tesseract
runtime and OCR files (including TSV output configuration), creates
`dist\RedactionTool.exe`, and runs headless tests for document redaction, OCR,
and Presidio. `RedactionTool.spec` intentionally stops if the binary assets are
missing rather than emitting an incomplete executable.

The single-file build will be large and may take longer to start because
PyInstaller extracts its bundled files to a temporary directory at launch.
Test the resulting executable on a clean machine without Python, Tesseract,
or network access before distributing it.

## Third-party notices

Before distributing the executable, retain notices for the bundled components
and verify their license/redistribution requirements: Presidio Analyzer (MIT),
spaCy and `en_core_web_sm` (MIT), Tesseract (Apache-2.0), Leptonica (BSD-style),
the Tesseract English model data, and all Python package dependencies. Include
those notices in the release materials.