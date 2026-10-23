# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Settings: loading, atomic saving and migration from the old INI file (FR-CFG, MIG-01)."""

from __future__ import annotations

import configparser
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import platformdirs

from pdf_multifile_searcher import APP_ID
from pdf_multifile_searcher.core.models import DEFAULT_CONTEXT_WORDS

log = logging.getLogger(__name__)

HISTORY_LIMIT = 20
LEGACY_INI = Path.home() / ".pdf_multifile_searcher_config.ini"


def default_config_path() -> Path:
    return Path(platformdirs.user_config_dir(APP_ID, appauthor=False)) / "settings.json"


@dataclass
class WindowState:
    x: int | None = None
    y: int | None = None
    width: int = 1200
    height: int = 800
    maximized: bool = False
    # Width of the left pane; the viewer takes the rest (FR-UI-02).
    sash: int = 540
    # Heights of folder tree / search area / results in the left pane.
    left_sizes: list[int] = field(default_factory=list)
    file_column_width: int = 170
    context_column_width: int = 380


@dataclass
class Settings:
    scopes: list[str] = field(default_factory=list)
    pattern: str = ""
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False
    history: list[str] = field(default_factory=list)
    context_words: int = DEFAULT_CONTEXT_WORDS
    use_cache: bool = True
    include_hidden: bool = False
    viewer_fit: str = "width"  # "width", "page" or "custom"
    viewer_zoom: float = 1.0
    sort_column: int = -1
    sort_descending: bool = False
    window: WindowState = field(default_factory=WindowState)

    def remember_pattern(self, pattern: str) -> None:
        """Put `pattern` at the top of the history (FR-SRCH-14)."""
        pattern = pattern.strip()
        if not pattern:
            return
        self.history = [pattern, *[p for p in self.history if p != pattern]][:HISTORY_LIMIT]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _coerce(type_name: str, value: Any, default: Any) -> Any:
    """Return `value` if it has the declared type, else `default` (FR-CFG-06)."""
    checks: dict[str, Any] = {
        "bool": lambda v: isinstance(v, bool),
        "int": _is_int,
        "int | None": lambda v: v is None or _is_int(v),
        "str": lambda v: isinstance(v, str),
        "float": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
        "list[str]": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
        "list[int]": lambda v: isinstance(v, list) and all(_is_int(i) for i in v),
    }
    check = checks.get(type_name)
    if check is None or not check(value):
        return default
    if type_name == "float":
        return float(value)
    return list(value) if isinstance(value, list) else value


def _from_dict(cls: type[Any], data: Any) -> Any:
    instance = cls()
    if not isinstance(data, dict):
        return instance
    for f in fields(cls):
        if f.name not in data:
            continue
        default = getattr(instance, f.name)
        if isinstance(default, WindowState):
            setattr(instance, f.name, _from_dict(WindowState, data[f.name]))
        else:
            setattr(instance, f.name, _coerce(str(f.type), data[f.name], default))
    return instance


def settings_from_dict(data: Any) -> Settings:
    settings: Settings = _from_dict(Settings, data)
    settings.scopes = [s for s in settings.scopes if isinstance(s, str) and s]
    settings.context_words = max(0, min(settings.context_words, 100))
    if settings.viewer_fit not in ("width", "page", "custom"):
        settings.viewer_fit = "width"
    settings.viewer_zoom = max(0.1, min(settings.viewer_zoom, 8.0))
    return settings


def migrate_legacy_ini(path: Path) -> Settings | None:
    """Import the old INI file (FR-CFG-08, MIG-01). The old file is not modified."""
    parser = configparser.ConfigParser(interpolation=None)
    try:
        if not parser.read(path, encoding="utf-8"):
            return None
    except (configparser.Error, OSError, UnicodeDecodeError) as exc:
        log.warning("Ignoring unreadable legacy configuration %s: %s", path, exc)
        return None
    settings = Settings()
    # The old format joins folders with commas, so paths containing commas cannot be
    # recovered; splitting on commas is the best possible interpretation.
    folders = parser.get("Folders", "folders", fallback="")
    settings.scopes = [f for f in folders.split(",") if f]
    settings.pattern = parser.get("Search", "pattern", fallback="")
    settings.remember_pattern(settings.pattern)

    def get_int(section: str, key: str, default: int | None) -> int | None:
        try:
            return parser.getint(section, key, fallback=default)  # type: ignore[arg-type]
        except ValueError:
            return default

    w = settings.window
    w.width = get_int("Window", "width", w.width) or w.width
    w.height = get_int("Window", "height", w.height) or w.height
    w.x = get_int("Window", "x", None)
    w.y = get_int("Window", "y", None)
    w.file_column_width = get_int("Treeview", "file_column_width", w.file_column_width) or 170
    w.context_column_width = (
        get_int("Treeview", "context_column_width", w.context_column_width) or 380
    )
    w.sash = get_int("Sash", "position", w.sash) or w.sash
    return settings


class ConfigStore:
    """Loads and saves settings. `persist_session` is False for command-line sessions,
    whose folders and pattern must not replace the saved ones (FR-CLI-04)."""

    def __init__(self, path: Path | None = None, legacy_path: Path | None = LEGACY_INI) -> None:
        self.path = path or default_config_path()
        self.legacy_path = legacy_path
        self.persist_session = True
        self._saved_scopes: list[str] = []
        self._saved_pattern = ""

    def load(self) -> Settings:
        settings: Settings | None = None
        if self.path.exists():
            try:
                with self.path.open(encoding="utf-8") as fh:
                    settings = settings_from_dict(json.load(fh))
            except (OSError, ValueError) as exc:
                log.warning("Ignoring unreadable configuration %s: %s", self.path, exc)
                settings = Settings()
        elif self.legacy_path is not None and self.legacy_path.exists():
            settings = migrate_legacy_ini(self.legacy_path)
            if settings is not None:
                log.info("Imported settings from %s", self.legacy_path)
                self.save(settings)
        settings = settings or Settings()
        self._saved_scopes = list(settings.scopes)
        self._saved_pattern = settings.pattern
        return settings

    def save(self, settings: Settings) -> None:
        """Write atomically: temporary file, then rename (FR-CFG-04)."""
        data = asdict(settings)
        if not self.persist_session:
            data["scopes"] = list(self._saved_scopes)
            data["pattern"] = self._saved_pattern
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".json", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            log.warning("Could not save configuration to %s: %s", self.path, exc)
