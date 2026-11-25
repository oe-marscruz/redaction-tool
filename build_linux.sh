#!/usr/bin/env bash
# Build the single-file Linux executable and validate it.
#
#   ./build_linux.sh                # .venv (created on first run) -> dist/RedactionTool
#   PYTHON=python3.12 ./build_linux.sh
#   ./build_linux.sh --skip-ocr-test
#
# The result is one self-contained file: Python runtime, Presidio + spaCy model,
# and (only if staged under vendor/tesseract) Tesseract. Without staged assets
# the binary uses the system `tesseract` found on PATH, which is the normal Linux
# arrangement — install it with your package manager (see README.md).
#
# Windows releases must stay fully bundled: use build_windows.ps1 there.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd -P)
cd "$ROOT"

SKIP_OCR_TEST=0
for arg in "$@"; do
    case "$arg" in
        --skip-ocr-test) SKIP_OCR_TEST=1 ;;
        -h|--help) awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

info() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

find_python() {
    for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if [ ! -x ".venv/bin/python" ]; then
    PYTHON=${PYTHON:-}
    if [ -z "$PYTHON" ]; then
        PYTHON=$(find_python) || die "Python 3.10+ not found; install python3 (and python3-venv on Debian/Ubuntu)."
    fi
    info "Creating .venv with $PYTHON ..."
    "$PYTHON" -m venv .venv || die "Could not create .venv (Debian/Ubuntu: sudo apt install python3-venv)."
fi
VENV_PY="$ROOT/.venv/bin/python"

# uv-created or --without-pip environments have no pip; add the bundled one.
if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 ||
        die "pip is missing from .venv and ensurepip failed; recreate .venv with 'python3 -m venv .venv'."
fi

# The spaCy model URL in requirements-presidio-optional.txt carries a
# #sha256= fragment, so pip verifies the download exactly like the Windows
# build verifies its pinned wheel.
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet \
    -r requirements.txt \
    -r requirements-presidio-optional.txt \
    "pyinstaller==6.22.0" || die "Dependency installation failed."

if [ ! -f "vendor/en_core_web_sm/meta.json" ]; then
    "$VENV_PY" scripts/stage_assets.py || die "Could not stage the spaCy model."
fi
[ -f "vendor/en_core_web_sm/meta.json" ] || die "vendor/en_core_web_sm/meta.json is missing."
[ -f "vendor/en_core_web_sm/en_core_web_sm-3.8.0/config.cfg" ] || die "Staged spaCy model files are incomplete."

"$VENV_PY" -c "import en_core_web_sm, presidio_analyzer, spacy; print('Presidio ready'); print('spaCy', spacy.__version__); print('Model', en_core_web_sm.__version__)"

OCR_ARGS=()
if [ -x "vendor/tesseract/tesseract" ]; then
    info "Staged Tesseract found: bundling OCR runtime."
    OCR_ARGS=(--require-ocr)
elif command -v tesseract >/dev/null 2>&1; then
    info "No staged Tesseract: the binary will use the system '$(command -v tesseract)'."
    if [ "$SKIP_OCR_TEST" -eq 0 ]; then
        OCR_ARGS=(--require-ocr)
    fi
else
    info "WARNING: Tesseract is not staged and not installed - OCR will be unavailable."
fi

"$VENV_PY" -m PyInstaller --noconfirm --clean RedactionTool.spec

SELFTEST="$ROOT/exe_selftest.txt"
rm -f "$SELFTEST"
set +e
"$ROOT/dist/RedactionTool" --selftest "$SELFTEST" ${OCR_ARGS[@]+"${OCR_ARGS[@]}"} --require-presidio
STATUS=$?
set -e
[ -f "$SELFTEST" ] || die "The packaged self-test did not write $SELFTEST."
cat "$SELFTEST"
[ "$STATUS" -eq 0 ] || die "Packaged self-test failed with exit $STATUS."
grep -q "PASS bundled Presidio" "$SELFTEST" || die "Packaged Presidio self-test did not pass."
if [ ${#OCR_ARGS[@]} -gt 0 ]; then
    grep -q "PASS bundled OCR" "$SELFTEST" || die "Packaged OCR self-test did not pass."
fi

info "Built $ROOT/dist/RedactionTool"
if command -v sha256sum >/dev/null 2>&1; then
    info "SHA-256: $(sha256sum dist/RedactionTool | cut -d' ' -f1)"
fi
info "Run it with: ./dist/RedactionTool   (menu entry: ./Run-RedactionTool.sh --install-desktop-entry)"
