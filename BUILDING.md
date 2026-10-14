# Building the single-file Windows executable

The release build is a **64-bit Windows one-file executable**. It bundles the
Python runtime, Presidio Analyzer, spaCy's English small model, Tesseract, and
English OCR trained data. The executable does not download any models or send
document text to a service.

## Offline & Release Security Guarantee

- **Zero Outbound Network at Runtime**: Redaction, OCR, and Presidio analysis operate entirely locally.
- **Dependency Freeze**: Pinned versions are `presidio-analyzer==2.2.364`, `spacy==3.8.11`, and `en_core_web_sm-3.8.0`.
- **Packaged Self-Test**: The build pipeline validates `dist\RedactionTool.exe` using `--selftest --require-ocr --require-presidio`.
- **Environment Status Gate**: If required local vendor assets or Python packages are missing on the build host, packaging/verification is reported as `BLOCKED (environment)`, never falsely marked as `PASS`.

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

### Release chain of custody

The build does not code-sign `dist\RedactionTool.exe` or the installer, so both
are unsigned and Windows SmartScreen will warn on first run. Before distributing
a release, record the provenance of the exact artifact:

- Build only from a reviewed commit that passed CI, and note the commit SHA.
- Record the SHA-256 of `dist\RedactionTool.exe` and of the compiled
  `installer\Output\RedactionTool-Setup-<version>.exe`, and publish those digests
  with the release so recipients can verify what they downloaded.
- Confirm `exe_selftest.txt` reports both `PASS bundled OCR` and
  `PASS bundled Presidio` for that artifact.
- Signing requires a code-signing certificate and is out of scope for this
  repository's build script; if a release needs a signed binary, add signing as
  a separate, reviewed step rather than treating the unsigned artifact as final.

## Installer (Inno Setup)

`build_windows.ps1` also compiles a per-user installer after the exe
self-test, **if Inno Setup 6 is installed**; otherwise it prints a warning
with install instructions and finishes successfully (the exe is the primary
artifact). Find it with:

```powershell
winget install --id JRSoftware.InnoSetup -e
```

The script locates `ISCC.exe` in `Program Files`, `Program Files (x86)`, and
`%LOCALAPPDATA%\Programs\Inno Setup 6`, then falls back to `iscc` on `PATH`.
To compile by hand:

```powershell
ISCC /DAppVersion=1.2.0 installer\RedactionTool.iss
```

Details:

- **`/DAppVersion`** sets the display version. It is single-sourced: the build
  script reads `__version__` from `redaction_tool/__init__.py` by importing
  `scripts/version_file.py` (`read_package_version()`) — bump `__version__`
  and nothing else. If you compile without `/DAppVersion`, a `0.0.0-dev`
  fallback is used for local checks only; releases must pass the real version.
- **Output**: `installer\Output\RedactionTool-Setup-<version>.exe`
  (gitignored). The `[Setup] VersionInfoVersion` fields are numeric-only, so
  the script strips any `-dev`/`-rc` suffix for those directives while
  `AppVersion`, `AppVerName`, and the output filename keep the full string —
  this is why `ISCC /DAppVersion=0.0.0-dev` compiles.
- **What it installs**: per-user (no UAC) into
  `{localappdata}\Programs\RedactionTool`, with a Start Menu entry and an
  uninstaller in Apps & Features. `installer\Code.iss` (included) detects and
  removes older installed versions, refuses downgrades unless `/ForceDowngrade`
  is passed, handles a running app, offers to clean up older portable exe
  copies, and never touches `%USERPROFILE%\.redaction_tool`.
- **CI**: `.github/workflows/ci.yml` has a `test` job that runs the unit,
  regression, security, Presidio integration, and end-to-end suites plus the
  synthetic evaluation corpus and the headless self-test, and an
  `installer-smoke` job that runs `build_windows.ps1` for real on
  `windows-latest`, asserts the packaged `PASS bundled OCR` and
  `PASS bundled Presidio` self-test lines, and uploads the resulting setup exe
  as the `installer-smoke` artifact. The build job verifies the pinned spaCy
  model hash via `scripts/check_model_pin.py` before building, so a malformed
  or drifted pin fails fast instead of only inside the release build.

## Third-party notices

Before distributing the executable, retain notices for the bundled components
and verify their license/redistribution requirements: Presidio Analyzer (MIT),
spaCy and `en_core_web_sm` (MIT), Tesseract (Apache-2.0), Leptonica (BSD-style),
the Tesseract English model data, and all Python package dependencies. Include
those notices in the release materials.
