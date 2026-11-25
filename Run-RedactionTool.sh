#!/usr/bin/env bash
# Redaction Tool launcher for Linux (and other POSIX desktops).
#
#   ./Run-RedactionTool.sh                     launch the app
#   ./Run-RedactionTool.sh --selftest out.txt  headless validation
#   ./Run-RedactionTool.sh --install-desktop-entry
#                                              add "Redaction Tool" to the
#                                              applications menu
#
# 1. If a built binary exists (dist/RedactionTool or ./RedactionTool) it runs
#    that — nothing to install.
# 2. Otherwise it runs from source: creates .venv on first run and installs
#    requirements.txt only when an import is missing.
#
# Windows users: use Run-RedactionTool.bat instead.
set -euo pipefail

# Resolve the directory this script lives in, following symlinks, so the app
# works when linked from ~/.local/bin.
SOURCE=${BASH_SOURCE[0]:-$0}
while [ -L "$SOURCE" ]; do
    DIR=$(CDPATH= cd -- "$(dirname -- "$SOURCE")" && pwd -P)
    SOURCE=$(readlink "$SOURCE")
    case $SOURCE in
        /*) ;;
        *) SOURCE=$DIR/$SOURCE ;;
    esac
done
APP_DIR=$(CDPATH= cd -- "$(dirname -- "$SOURCE")" && pwd -P)
cd "$APP_DIR"

info() { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

desktop_entry_path() {
    printf '%s\n' "${XDG_DATA_HOME:-$HOME/.local/share}/applications/redaction-tool.desktop"
}

install_desktop_entry() {
    local target="$APP_DIR/Run-RedactionTool.sh"
    if [ -x "$APP_DIR/dist/RedactionTool" ]; then
        target="$APP_DIR/dist/RedactionTool"
    elif [ -x "$APP_DIR/RedactionTool" ]; then
        target="$APP_DIR/RedactionTool"
    fi
    local dest
    dest=$(desktop_entry_path)
    mkdir -p "$(dirname "$dest")"
    cat >"$dest" <<DESKTOP
[Desktop Entry]
Type=Application
Version=1.0
Name=Redaction Tool
GenericName=Document Redaction Tool
Comment=Permanently redact FERPA / HIPAA identifiers from PDF, DOCX and XLSX files
Exec="$target"
Terminal=false
Categories=Office;
Keywords=redaction;anonymise;anonymize;FERPA;HIPAA;PDF;DOCX;XLSX;
DESKTOP
    chmod 644 "$dest"
    info "Installed menu entry: $dest"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$(dirname "$dest")" >/dev/null 2>&1 || true
    fi
    info "Launch it from your applications menu, or run: $target"
}

find_python() {
    local fallback=""
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        command -v "$candidate" >/dev/null 2>&1 || continue
        "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null || continue
        if "$candidate" -c 'import tkinter' 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
        : "${fallback:=$candidate}"
    done
    if [ -n "$fallback" ]; then
        printf '%s\n' "$fallback"
        return 0
    fi
    return 1
}

case ${1:-} in
    -h|--help)
        awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
        exit 0
        ;;
    --install-desktop-entry)
        install_desktop_entry
        exit 0
        ;;
esac

# ── 1. Prebuilt binary (self-contained, preferred) ────────────────────────
for binary in "dist/RedactionTool" "RedactionTool"; do
    if [ -x "$binary" ]; then
        exec "$(pwd -P)/$binary" "$@"
    fi
done

# ── 2. Source mode ────────────────────────────────────────────────────────
PYTHON=${PYTHON:-}
if [ -z "$PYTHON" ]; then
    PYTHON=$(find_python) || fail "Python 3.10+ was not found.
  Install it with your package manager, e.g.:
    Debian/Ubuntu: sudo apt install python3 python3-venv python3-tk
    Fedora:        sudo dnf install python3 python3-tkinter
    Arch:          sudo pacman -S python tk"
fi

if [ ! -x ".venv/bin/python" ]; then
    info "Creating virtual environment (first run only)..."
    if ! "$PYTHON" -m venv .venv; then
        fail "Could not create .venv. On Debian/Ubuntu install python3-venv first:
    sudo apt install python3-venv"
    fi
fi
VENV_PY=.venv/bin/python

if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 ||
        fail "pip is missing from .venv and could not be bootstrapped.
    Recreate the environment: rm -rf .venv && ./Run-RedactionTool.sh"
fi

if ! "$VENV_PY" -c 'import tkinter' 2>/dev/null; then
    fail "This Python has no tkinter ('$PYTHON'). Install the Tk bindings and retry:
    Debian/Ubuntu: sudo apt install python3-tk
    Fedora:        sudo dnf install python3-tkinter
    Arch:          sudo pacman -S tk
  Then delete .venv and run this script again."
fi

if ! "$VENV_PY" -c 'import pymupdf, docx, openpyxl, tkinterdnd2' 2>/dev/null; then
    info "Installing required packages into .venv ..."
    "$VENV_PY" -m pip install --quiet --upgrade pip
    "$VENV_PY" -m pip install --quiet -r requirements.txt ||
        fail "Dependency installation failed. Check your internet connection."
fi

exec "$VENV_PY" run.py "$@"
