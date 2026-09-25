"""Generate a PyInstaller VSVersionInfo file from redaction_tool.__version__.

The package version in redaction_tool/__init__.py is the single source of
truth for both the app and the Windows version resource on the built exe.

Run directly to (re)generate the file:
    python scripts/version_file.py

The PyInstaller spec (RedactionTool.spec) imports this module and calls
generate() at build time, so bumping __version__ is the only edit needed.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_PY = ROOT / "redaction_tool" / "__init__.py"
VERSION_FILE = ROOT / "build" / "version_info.txt"

FILE_DESCRIPTION = "Redaction Tool"
PRODUCT_NAME = "Redaction Tool"
INTERNAL_NAME = "RedactionTool.exe"
ORIGINAL_FILENAME = "RedactionTool.exe"


def read_package_version() -> str:
    """Parse the ``__version__`` assignment without importing the package."""
    text = INIT_PY.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not match:
        raise ValueError(f"No __version__ assignment found in {INIT_PY}")
    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int, int]:
    """Coerce a version string to four numeric parts for VSVersionInfo.

    Handles prerelease/suffix versions gracefully: "1.2.0", "1.2.0-rc.1",
    and "1.2" all yield numeric tuples, missing parts default to 0, and any
    non-numeric tail is dropped.
    """
    core = version.strip().split("-", 1)[0].split("+", 1)[0]
    parts = []
    for token in core.split("."):
        digits = re.match(r"\d+", token)
        parts.append(int(digits.group()) if digits else 0)
        if len(parts) == 4:
            break
    if not parts:
        raise ValueError(f"Version {version!r} has no numeric parts")
    parts += [0] * (4 - len(parts))
    return tuple(parts)


def render(version: str) -> str:
    nums = parse_version(version)
    flat = ", ".join(str(n) for n in nums)
    version_tuple = f"({flat})"
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', '{PRODUCT_NAME}'),
          StringStruct('FileDescription', '{FILE_DESCRIPTION}'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', '{INTERNAL_NAME}'),
          StringStruct('OriginalFilename', '{ORIGINAL_FILENAME}'),
          StringStruct('ProductName', '{PRODUCT_NAME}'),
          StringStruct('ProductVersion', '{version}'),
        ])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
"""


def generate() -> Path:
    """Write the version file for the current package version."""
    version = read_package_version()
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(render(version), encoding="utf-8")
    return VERSION_FILE


if __name__ == "__main__":
    path = generate()
    print(f"Wrote {path} for version {read_package_version()}")
