"""Verify the pinned spaCy model SHA-256 is well-formed and consistent.

``build_windows.ps1`` compares ``Get-FileHash`` output against its pinned
constant. ``Get-FileHash`` always returns exactly 64 hex characters, so a
constant of any other length makes that comparison throw unconditionally and
no artifact can ever be produced. ``requirements-presidio-optional.txt``
declares the same digest for the downloadable wheel, so the two must agree.

Run from the repository root.
"""

from __future__ import annotations

import pathlib
import re
import sys

BUILD_SCRIPT = pathlib.Path("build_windows.ps1")
REQUIREMENTS = pathlib.Path("requirements-presidio-optional.txt")
EXPECTED_LENGTH = 64
_DIGEST_RE = re.compile(r"^[0-9A-Fa-f]+$")


def extract(script: str, requirements: str) -> tuple[str, str]:
    match = re.search(r'modelSha256\s*=\s*"([^"]*)"', script)
    if not match:
        raise ValueError("could not read the pinned model hash from build_windows.ps1")
    declared = re.search(r"sha256=([0-9A-Fa-f]+)", requirements)
    if not declared:
        raise ValueError(
            "could not read the declared model hash from requirements-presidio-optional.txt"
        )
    return match.group(1).strip(), declared.group(1).strip()


def main() -> int:
    pinned, declared = extract(
        BUILD_SCRIPT.read_text(encoding="utf-8"),
        REQUIREMENTS.read_text(encoding="utf-8"),
    )

    if not _DIGEST_RE.match(pinned):
        print(f"FAIL: build_windows.ps1 pin is not hexadecimal: {pinned!r}")
        return 1
    if len(pinned) != EXPECTED_LENGTH:
        print(
            f"FAIL: build_windows.ps1 pin is {len(pinned)} chars, "
            f"expected {EXPECTED_LENGTH}: {pinned!r}"
        )
        return 1
    if pinned.upper() != declared.upper():
        print("FAIL: build_windows.ps1 pin does not match requirements-presidio-optional.txt")
        print(f"  build_windows.ps1                : {pinned.upper()}")
        print(f"  requirements-presidio-optional.txt: {declared.upper()}")
        return 1

    print(
        "PASS: pinned spaCy model SHA-256 is 64 hex chars and matches the "
        "declared requirement."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
