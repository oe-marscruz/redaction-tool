# -*- mode: python ; coding: utf-8 -*-
"""Single-file Windows bundle. Run build_windows.ps1 to validate asset inputs."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
TESSERACT = ROOT / "vendor" / "tesseract"
MODEL = ROOT / "vendor" / "en_core_web_sm"
TESSERACT_RUNTIME_DLLS = list(TESSERACT.rglob("*.dll"))
if not TESSERACT_RUNTIME_DLLS:
    TESSERACT_RUNTIME_DLLS = list(TESSERACT.rglob("*.pyd"))

required_files = [
    TESSERACT / "tesseract.exe",
    TESSERACT / "tessdata" / "eng.traineddata",
    TESSERACT / "tessdata" / "configs" / "tsv",
    MODEL / "meta.json",
]
missing = [str(path) for path in required_files if not path.is_file()]
if not MODEL.is_dir() or not (MODEL / "en_core_web_sm-3.8.0" / "config.cfg").is_file():
    missing.append(f"{MODEL} (spaCy model package data, including config.cfg)")
if not TESSERACT_RUNTIME_DLLS:
    missing.append(f"{TESSERACT} (Tesseract runtime DLLs)")
if missing:
    raise SystemExit(
        "Missing offline build assets:\n  " + "\n  ".join(missing)
        + "\nSee BUILDING.md for setup instructions."
    )

datas, binaries, hiddenimports = [], [], []

# Tcl/Tk resources are loaded dynamically by tkinterdnd2.
d, b, h = collect_all("tkinterdnd2")
datas += d
binaries += b
hiddenimports += h

# spaCy's compiled pipeline package and Presidio modules use dynamic imports.
for package in ("spacy", "presidio_analyzer"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

# spaCy model code is an importable package; its model weights/configuration
# are staged separately as runtime data below.
d, b, h = collect_all("en_core_web_sm")
hiddenimports += h
binaries += b

for path in MODEL.rglob("*"):
    if path.is_file():
        datas.append((str(path), str(Path("en_core_web_sm") / path.relative_to(MODEL).parent)))

datas += [
    *[(str(path), str(Path("tesseract/tessdata") / path.relative_to(TESSERACT / "tessdata").parent))
      for path in (TESSERACT / "tessdata").rglob("*") if path.is_file()],
]

# Only bundle the OCR CLI, its shared libraries, and runtime data (including eng).
binaries += [(str(path), str(Path("tesseract") / path.relative_to(TESSERACT).parent))
            for path in TESSERACT_RUNTIME_DLLS]
binaries += [(str(TESSERACT / "tesseract.exe"), "tesseract")]
for path in TESSERACT.rglob("*"):
    if not path.is_file() or path.suffix.lower() in {".dll", ".pyd", ".exe"}:
        continue
    if path.is_relative_to(TESSERACT / "tessdata"):
        relative = Path("tesseract/tessdata") / path.relative_to(TESSERACT / "tessdata").parent
    else:
        relative = Path("tesseract") / path.relative_to(TESSERACT).parent
    datas.append((str(path), str(relative)))

hiddenimports += [
    "pymupdf",
    "fitz",
    "docx",
    "openpyxl",
    "openpyxl.cell._writer",
    "presidio_analyzer",
    "spacy",
    "en_core_web_sm",
]

a = Analysis(
    ["run.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RedactionTool",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)