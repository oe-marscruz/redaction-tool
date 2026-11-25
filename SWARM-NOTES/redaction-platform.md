# redaction-platform — Linux parity for a Windows-only desktop tool

Lane: `swarm/platform`. Worktree: `~/Projects/tribrigade-swarm/lanes/redaction-platform`
(branch `swarm/platform`). Scope: platform/config/launcher/build/CI/docs plus the
minimum touch-points in `redaction_tool/` and `run.py` needed to make the app
start and find its dependencies on Linux. Detection quality and GUI features
belong to the `redaction-product` lane and were not touched.

## 1. Audit (Linux, this machine)

Environment: Arch Linux, system Python 3.14 without shared `libtk`;
`uv venv -p 3.13` (CPython 3.13.14, Tcl/Tk **9.0**), Tesseract 5.5.4 with
`/usr/share/tessdata/{eng.traineddata,configs/tsv}`.

Ran the exact command list from `.github/workflows/ci.yml` (windows job):

| Command | Linux result |
|---|---|
| `python tests/test_core.py` | **FAIL** — `ERROR test_image_round_trip: RuntimeError: Tesseract English data (eng.traineddata) was not found` |
| `python tests/test_high_recall.py` | ALL PASS |
| `python tests/test_presidio_integration.py` | ALL PASS |
| `python -m unittest tests/test_document_context.py` | 14 tests OK |
| `python -m unittest tests/test_security_verification.py` | 15 tests OK |
| `python -m unittest tests/test_end_to_end_presidio.py` | 5 tests OK |
| `python tests/eval_metrics.py` | exit 0, `A/B Comparison: PASS` |
| `python run.py --selftest result.txt` | `OK`, DOCX/XLSX/PDF + image render PASS |
| `python run.py` (GUI, under `xvfb-run`) | **crash**: `RuntimeError: Unable to load tkdnd library` |

Root causes found by reading and probing:

1. **GUI cannot start on Linux with Tk 9.** `tkinterdnd2` imports fine
   (`_DND_OK = True`) but `TkinterDnD.Tk()` raises because its bundled
   `libtkdnd2.9.5.so` reports `this extension is compiled for Tcl 8.x`.
   `gui.main()` picks `TkinterDnD.Tk()` based on the import alone, so the whole
   app dies. (Ubuntu 24.04's `python3-tk` is Tk 8.6 and would work; uv,
   python-build-standalone and future distros ship Tk 9, so this is the default
   experience for most new Linux users.)
2. **Tesseract data discovery is Windows-only.** `find_tessdata()` probes
   `vendor/tesseract*`, `TESSDATA_PREFIX`, `<exe>/tessdata`, and two
   `C:\Program Files` paths — never `/usr/share/tessdata` or
   `/usr/share/tesseract-ocr/*/tessdata`, which is where distro packages put
   it. `find_tesseract()` likewise looks for `tesseract.exe` first and relies on
   `PATH` as the only POSIX fallback. `find_tessdata()` also hard-requires
   `configs/tsv`, so a data dir without the config file is rejected outright.
3. **Settings/presets location is a raw `Path.home()`.** It happens to work on
   Linux but ignores the XDG base-dir spec and mixes the tool's dotfiles into
   `$HOME`. Windows must keep `%USERPROFILE%\.redaction_tool` for backward
   compatibility with installed users.
4. **No Linux launcher.** `Run-RedactionTool.bat` is the only double-click
   path; there is no shell launcher and no menu entry, so a Linux user must
   hand-write the venv commands.
5. **Build is Windows-only.** `RedactionTool.spec` hard-codes
   `vendor/tesseract/tesseract.exe`, `*.dll/*.pyd`, and a Windows version
   resource; `build_windows.ps1` is PowerShell. There is no documented or
   automated way to produce a Linux binary.
6. **CI is Windows-only** (`windows-latest` for both jobs). The PR scope/safety
   gate is an inline `python -c` heredoc duplicated nowhere but also reusable
   nowhere.
7. **`--selftest --require-ocr` uses `C:/Windows/Fonts/arial.ttf`**, falling back
   to a tiny bitmap font on Linux that OCR cannot read — the OCR self-test that
   guards release builds would fail on any non-Windows package.
8. **`.gitignore` ends with a UTF-16LE `result.txt` line** (`r\0e\0s\0...`), so
   the CI-created `result.txt` is not actually ignored.
9. `validate_real_files.py` requires editing source to name input files
   (`TEST_FILES` placeholders under `path/to/`), and `PROJECT` points at the
   repository's *parent* directory, so the defaults can never resolve. It is a
   manual harness with no way to point it at a corpus from the command line.

## 2. Comparison with comparable open-source projects

| Project | What it does | Taken | Rejected / why |
|---|---|---|---|
| [dynobo/NormCap](https://github.com/dynobo/NormCap) (~2.8k★) | Cross-platform Python/Tk-adjacent OCR desktop app | Per-OS install docs; Linux needs distro Tesseract (`apt install tesseract-ocr tesseract-ocr-eng`, `pacman -S tesseract tesseract-data-eng`) documented next to the "bundled" option; config in the OS-appropriate directory | Flatpak/AppImage/AUR publishing — out of MVP scope and unverifiable here |
| [pdfarranger/pdfarranger](https://github.com/pdfarranger/pdfarranger) (~6k★) | Python desktop PDF GUI, Linux-first, Windows port | Ship a `.desktop` entry + document distro packages per family; keep the GUI usable without optional system extensions (graceful degradation) | MSYS2/GTK packaging — different toolkit, no benefit for a Tk app |
| [freedomofpress/dangerzone](https://github.com/freedomofpress/dangerzone) (~5.9k★) | Cross-platform document sanitizer with per-OS builds | Prove the non-Windows build path in CI on a real runner instead of only documenting it; split user docs by OS | Container sandbox architecture — out of scope |
| [firstlookmedia/pdf-redact-tools](https://github.com/firstlookmedia/pdf-redact-tools) (~550★) | Shell-based PDF redaction helper | Confirmation that shelling out to ImageMagick/Ghostscript is a maintenance and security trap; we stay in-process with PyMuPDF | The whole approach: unmaintained, ImageMagick CVEs, pointed users at Dangerzone |
| [JoshData/pdf-redactor](https://github.com/JoshData/pdf-redactor) (~210★) | Pure-Python PDF text-layer redactor | Explicit "Limitations" docs and a `pip`-installable footprint are what make small privacy tools adoptable; adopt the honest caveats style | Library-only design, no verification/audit trail |

## 3. Ranked improvements (impact × effort)

| # | Change | Impact | Effort |
|---|---|---|---|
| 1 | GUI startup fallback when the `tkdnd` extension cannot load | Critical (app does not start) | S |
| 2 | Linux Tesseract + tessdata discovery (incl. `--list-langs` probe, TSV config fallback) | Critical (OCR on Linux) | S |
| 3 | Cross-platform user data dir (XDG on Linux, legacy `~/.redaction_tool` / `%USERPROFILE%\.redaction_tool` kept) | High | S |
| 4 | `Run-RedactionTool.sh` launcher + `--install-desktop-entry` (`.desktop`) | High (stranger can run it) | S |
| 5 | Linux PyInstaller path: platform-aware spec + `build_linux.sh` | High (shippable binary) | M |
| 6 | `ubuntu-latest` CI job mirroring the Windows test job; shared scope-gate script | High (regression proof) | S |
| 7 | README quickstart for Linux **and** Windows; BUILDING.md Linux section | High (discoverability) | S |
| 8 | `--selftest` OCR font fallback (non-Windows packages) | Medium (release gate) | XS |
| 9 | `validate_real_files.py` accepts CLI paths, repo-root-relative, fixed scan call | Medium (usable harness) | XS |
| 10 | `.gitignore` UTF-16 line fix | Low | XS |

## 4. Chosen scope

All of the above (1–10). Deliberately **not** done:

- Bundle a Linux Tesseract (system package is the norm on Linux and the license
  provenance/vendoring rules in `BUILDING.md` forbid committing binaries).
- Add a Flatpak/AppImage/.deb — none of it is verifiable from this worktree and
  the repo's CI forbids committed binaries.
- Touch detection heuristics, presets content, or the GUI layout/theme
  (that is the `redaction-product` lane).

Windows compatibility rules followed: every path change is `os.name == "nt"`
gated with the exact legacy string; the spec keeps byte-identical asset paths
and the version resource on Windows; `build_windows.ps1`,
`Run-RedactionTool.bat` and the `installer-smoke` job are untouched except where
the shared CI gate replaces an inline duplicate.
