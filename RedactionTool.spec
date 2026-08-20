# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build config for the Redaction Tool.

Produces a single-file, windowed (no console) executable that bundles the
Python runtime and every dependency — PyMuPDF, python-docx, openpyxl and
tkinterdnd2 (including its tkdnd binaries for drag & drop).  The target
machine needs nothing installed.

Build:
    .venv\\Scripts\\pyinstaller.exe --noconfirm RedactionTool.spec

Validate the packaged exe headlessly:
    dist\\RedactionTool.exe --selftest result.txt
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []

# tkinterdnd2 ships tkdnd .dll/.tcl files that must be collected explicitly.
for pkg in ("tkinterdnd2",):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += [
    "pymupdf",
    "fitz",
    "docx",
    "openpyxl",
    "openpyxl.cell._writer",
]

a = Analysis(
    ["run.py"],
    pathex=[],
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
    upx=False,              # UPX triggers AV false positives; keep off
    console=False,          # windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
