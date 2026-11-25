"""PR scope & safety gate shared by the Windows and Linux CI jobs.

Rejects changes to the pinned dependency files and committed binary/vendor
assets. Run locally with ``python scripts/ci_scope_gate.py`` from a checkout
that has ``origin/main`` fetched.
"""

import pathlib
import subprocess
import sys

FORBIDDEN_DEPS = {"requirements.txt", "requirements-presidio-optional.txt"}
BINARY_EXTS = {
    ".dll", ".exe", ".bin", ".whl", ".traineddata", ".so", ".dylib", ".pyd",
    ".onnx", ".safetensors",
}


def changed_files() -> list[str]:
    res = subprocess.run(["git", "diff", "--name-only", "origin/main...HEAD"],
                         capture_output=True, text=True)
    changed = [f.strip() for f in res.stdout.splitlines() if f.strip()]
    if not changed:
        res = subprocess.run(["git", "diff", "--name-only", "HEAD~1"],
                             capture_output=True, text=True)
        changed = [f.strip() for f in res.stdout.splitlines() if f.strip()]
    return changed


def main() -> int:
    print("=== PR Scope & Changed Path Check ===")
    changed = changed_files()
    print("Changed files:")
    if changed:
        for path in changed:
            print("  " + path)
    else:
        print("  None")

    forbidden_mod = [f for f in changed if f in FORBIDDEN_DEPS]
    if forbidden_mod:
        print("SAFETY GATE REJECTED: Modified forbidden dependency files:", forbidden_mod)
        return 1

    forbidden_bin = [f for f in changed
                     if pathlib.Path(f).suffix.lower() in BINARY_EXTS
                     or "vendor/" in f.replace("\\", "/").lower()]
    if forbidden_bin:
        print("SAFETY GATE REJECTED: Detected committed model/vendor binary files:",
              forbidden_bin)
        return 1

    print("SAFETY GATE PASSED: Dependency files untouched and no committed binaries "
          "detected. Note: Path scope checks provide structural path safeguards, "
          "not semantic proof against feature creep.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
