@echo off
REM ─────────────────────────────────────────────────────────────────────
REM  Redaction Tool launcher
REM
REM  1. If the standalone exe exists, runs it (nothing to install).
REM  2. Otherwise runs from source: creates a venv and auto-installs any
REM     missing Python dependencies, then launches the app.
REM ─────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

REM ── 1. Standalone exe (fully self-contained — preferred) ─────────────
if exist "dist\RedactionTool.exe" (
    start "" "dist\RedactionTool.exe"
    exit /b 0
)
if exist "RedactionTool.exe" (
    start "" "RedactionTool.exe"
    exit /b 0
)

REM ── 2. Source mode requires Python ────────────────────────────────────
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo  Python was not found on this computer.
    echo.
    echo  Either:
    echo    a) Use the standalone build:  dist\RedactionTool.exe
    echo    b) Install Python 3.11+ from https://www.python.org/downloads/
    echo       ^(tick "Add python.exe to PATH" during install^)
    echo.
    pause
    exit /b 1
)

REM ── 3. Create the virtual environment on first run ────────────────────
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment ^(first run only^)...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

REM ── 4. Install dependencies only when something is missing ────────────
.venv\Scripts\python.exe -c "import pymupdf, docx, openpyxl, tkinterdnd2" 2>nul
if errorlevel 1 (
    echo Installing required packages...
    .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
)

REM ── 5. Launch (pythonw = no console window) ───────────────────────────
start "" ".venv\Scripts\pythonw.exe" run.py
exit /b 0
