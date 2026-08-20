"""Preset management for redaction categories.

Built-in presets: "FERPA Only", "HIPAA Only", "Full (FERPA + HIPAA)".
Users can create, save, load, and delete custom presets stored as JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from .detector import CATEGORIES, CATEGORY_MAP, PRESETS

# Path for user presets (stored next to the tool or in user config)
_PRESETS_DIR = Path.home() / ".redaction_tool" / "presets"


def _ensure_dir() -> None:
    _presets_dir().mkdir(parents=True, exist_ok=True)


def _presets_dir() -> Path:
    return _PRESETS_DIR


def _preset_path(name: str) -> Path:
    safe = "".join(c for c in name if c.isalnum() or c in " _-").rstrip()
    return _presets_dir() / f"{safe}.json"


def builtin_presets() -> dict[str, list[str]]:
    """Return a copy of the built-in preset definitions."""
    return {k: list(v) for k, v in PRESETS.items()}


def all_category_keys() -> list[str]:
    """Return every available category key."""
    return [c.key for c in CATEGORIES]


def all_category_labels() -> dict[str, str]:
    """Return ``{key: label}`` for every category."""
    return {c.key: c.label for c in CATEGORIES}


def save_preset(name: str, category_keys: list[str]) -> Path:
    """Save a custom preset to disk.  Returns the file path."""
    _ensure_dir()
    path = _preset_path(name)
    data = {"name": name, "categories": category_keys}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_presets() -> dict[str, list[str]]:
    """Load all custom presets from disk.

    Returns ``{name: [category_keys]}``.
    """
    _ensure_dir()
    presets: dict[str, list[str]] = {}
    for f in sorted(_presets_dir().glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "name" in data and "categories" in data:
                presets[data["name"]] = data["categories"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return presets


def delete_preset(name: str) -> bool:
    """Delete a custom preset.  Returns True if deleted."""
    path = _preset_path(name)
    if path.exists():
        path.unlink()
        return True
    return False


def list_all_presets() -> dict[str, list[str]]:
    """Return built-in + custom presets (custom overrides built-in by name)."""
    all_presets = builtin_presets()
    all_presets.update(load_presets())
    return all_presets
