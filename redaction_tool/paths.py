"""Where the app keeps user state (settings, saved presets).

Windows keeps the historical location ``%USERPROFILE%\\.redaction_tool`` so an
upgrade never loses presets from an earlier install.  Linux and other POSIX
systems use the XDG base-dir location (``$XDG_CONFIG_HOME/redaction-tool``,
default ``~/.config/redaction-tool``).

If a legacy ``~/.redaction_tool`` directory already exists and the XDG location
does not, the legacy directory keeps being used: source users who ran the tool
before the XDG move keep their presets instead of silently starting over.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "redaction-tool"
LEGACY_DIR_NAME = ".redaction_tool"


def _is_windows() -> bool:
    return os.name == "nt"


def _legacy_dir() -> Path:
    """The pre-XDG dot directory, also the current Windows location."""
    return Path.home() / LEGACY_DIR_NAME


def _xdg_base_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    if xdg and Path(xdg).is_absolute():
        return Path(xdg)
    return Path.home() / ".config"


def user_data_dir() -> Path:
    """Directory holding ``settings.json`` and ``presets/``.

    The directory is not created by this function; callers create it when they
    first write (presets and theme settings are both optional).
    """
    if _is_windows():
        return _legacy_dir()
    xdg_dir = _xdg_base_dir() / APP_DIR_NAME
    legacy = _legacy_dir()
    if not xdg_dir.exists() and legacy.is_dir():
        return legacy
    return xdg_dir


def settings_path() -> Path:
    return user_data_dir() / "settings.json"


def presets_dir() -> Path:
    return user_data_dir() / "presets"
