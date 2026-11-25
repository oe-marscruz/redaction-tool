# -*- mode: python ; coding: utf-8 -*-
"""Single-file bundle (Windows and Linux).

Windows: run ``build_windows.ps1`` — it validates the staged Tesseract and
spaCy assets and fails the build when they are missing.

Linux: run ``build_linux.sh``. A Linux build bundles Tesseract only when the
runtime was staged under ``vendor/tesseract``; otherwise the binary uses the
system ``tesseract`` found on ``PATH`` (see BUILDING.md).
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)
IS_WINDOWS = sys.platform == "win32"

# Windows version resource for the exe, generated from
# redaction_tool/__init__.py.__version__ (the single source of truth).
# Non-Windows executables have no version resource to fill in.
version_file = None
if IS_WINDOWS:
    sys.path.insert(0, str(ROOT / "scripts"))
    from version_file import generate as generate_version_file  # noqa: E402

    version_file = str(generate_version_file())

TESSERACT = ROOT / "vendor" / "tesseract"
MODEL = ROOT / "vendor" / "en_core_web_sm"
TESSERACT_EXE = TESSERACT / ("tesseract.exe" if IS_WINDOWS else "tesseract")
LIB_SUFFIXES = {".dll", ".pyd"} if IS_WINDOWS else {".so"}
TESSERACT_RUNTIME_LIBS = [
    path for path in TESSERACT.rglob("*") if path.suffix in LIB_SUFFIXES
]
BUNDLE_OCR = IS_WINDOWS or TESSERACT_EXE.is_file()

required_files = [
    TESSERACT_EXE,
    TESSERACT / "tessdata" / "eng.traineddata",
    TESSERACT / "tessdata" / "configs" / "tsv",
    MODEL / "meta.json",
]
missing = [str(path) for path in required_files if not path.is_file()]
if not MODEL.is_dir() or not (MODEL / "en_core_web_sm-3.8.0" / "config.cfg").is_file():
    missing.append(f"{MODEL} (spaCy model package data, including config.cfg)")
if BUNDLE_OCR and not TESSERACT_RUNTIME_LIBS:
    missing.append(f"{TESSERACT} (Tesseract runtime libraries)")

# On Linux the OCR runtime is optional: distro packages provide Tesseract, and
# bundling a system Tesseract plus its shared libraries is not something this
# project can verify in CI. Windows releases must stay fully self-contained.
if not IS_WINDOWS and not BUNDLE_OCR:
    missing = [path for path in missing if not path.startswith(str(TESSERACT))]
    print("RedactionTool.spec: no vendor/tesseract staged - building "
          "without bundled OCR; the app will use the system 'tesseract'.")
if missing:
    raise SystemExit(
        "Missing offline build assets:\n  " + "\n  ".join(missing)
        + "\nSee BUILDING.md for setup instructions."
    )

datas, binaries, hiddenimports = [], [], []

if not IS_WINDOWS:
    # PyInstaller's tkinter hook bundles Tcl/Tk *data* but does not resolve the
    # Tcl/Tk shared libraries when the interpreter keeps them outside the
    # system loader path (uv and python-build-standalone put them in
    # <prefix>/lib). Ship them next to the executable so _tkinter can load.
    import sysconfig

    tcl_dirs = {
        Path(value) for value in (
            sysconfig.get_config_var("LIBDIR"),
            str(Path(sys.base_prefix) / "lib"),
            str(Path(sys.prefix) / "lib"),
        ) if value
    }
    shipped: set[str] = set()
    for directory in sorted(tcl_dirs):
        if not directory.is_dir():
            continue
        for pattern in ("libtcl*.so*", "libtk*.so*"):
            for lib in sorted(directory.glob(pattern)):
                if lib.name in shipped:
                    continue
                shipped.add(lib.name)
                binaries.append((str(lib), "."))

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

if BUNDLE_OCR:
    tesseract_datas = [
        *[(str(path), str(Path("tesseract/tessdata") / path.relative_to(TESSERACT / "tessdata").parent))
          for path in (TESSERACT / "tessdata").rglob("*") if path.is_file()],
    ]
    datas += tesseract_datas

    # Only bundle the OCR CLI, its shared libraries, and runtime data (including eng).
    binaries += [(str(path), str(Path("tesseract") / path.relative_to(TESSERACT).parent))
                for path in TESSERACT_RUNTIME_LIBS]
    binaries += [(str(TESSERACT_EXE), "tesseract")]
    for path in TESSERACT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in LIB_SUFFIXES | {".exe"}:
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
    # python-docx locates its header/footer templates relative to the source
    # file (``docx/parts/../templates``), and that traversal fails when only the
    # package's bytecode lives in the PYZ archive with no ``docx/parts``
    # directory on disk. Keeping the sources on disk as well makes the packaged
    # build read the same templates the source checkout does.
    module_collection_mode={"docx": "pyz+py"},
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RedactionTool",
    version=version_file,
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
