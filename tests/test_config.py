# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Settings round trip, robustness and INI migration (FR-CFG, MIG-01, FR-CLI-04)."""

from __future__ import annotations

import json
from pathlib import Path

from pdf_multifile_searcher.config import HISTORY_LIMIT, ConfigStore, Settings


def test_round_trip_with_awkward_paths(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "settings.json", legacy_path=None)
    settings = Settings(scopes=["/data/a,b", "/data/x=y", "/Dokumente/Über"], pattern="ä, ö")
    settings.window.left_sizes = [100, 300]
    store.save(settings)
    loaded = ConfigStore(tmp_path / "settings.json", legacy_path=None).load()
    assert loaded == settings


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    assert ConfigStore(tmp_path / "none.json", legacy_path=None).load() == Settings()


def test_corrupt_file_gives_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    assert ConfigStore(path, legacy_path=None).load() == Settings()


def test_wrong_types_fall_back_per_field(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "scopes": "not a list",
                "pattern": "kept",
                "context_words": "ten",
                "window": {"width": "wide", "height": 700, "left_sizes": ["a"]},
                "viewer_fit": "nonsense",
            }
        )
    )
    loaded = ConfigStore(path, legacy_path=None).load()
    assert loaded.scopes == [] and loaded.pattern == "kept"
    assert loaded.context_words == Settings().context_words
    assert loaded.window.width == 1200 and loaded.window.height == 700
    assert loaded.window.left_sizes == [] and loaded.viewer_fit == "width"


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path / "settings.json", legacy_path=None)
    store.save(Settings(pattern="x"))
    store.save(Settings(pattern="y"))
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_legacy_ini_is_imported_once(tmp_path: Path) -> None:
    legacy = tmp_path / "old.ini"
    legacy.write_text(
        "[Folders]\nfolders = /a,/b\n\n[Search]\npattern = needle\n\n"
        "[Window]\nwidth = 1000\nheight = 700\nx = 10\ny = 20\n\n"
        "[Treeview]\nfile_column_width = 250\ncontext_column_width = 300\n\n"
        "[Sash]\nposition = 333\n"
    )
    original = legacy.read_text()
    store = ConfigStore(tmp_path / "new" / "settings.json", legacy_path=legacy)
    settings = store.load()
    assert settings.scopes == ["/a", "/b"]
    assert settings.pattern == "needle" and settings.history == ["needle"]
    w = settings.window
    assert (w.width, w.height, w.x, w.y, w.sash) == (1000, 700, 10, 20, 333)
    assert w.file_column_width == 250
    assert (tmp_path / "new" / "settings.json").exists()
    assert legacy.read_text() == original


def test_cli_session_does_not_overwrite_saved_scopes(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    ConfigStore(path, legacy_path=None).save(Settings(scopes=["/saved"], pattern="saved"))
    store = ConfigStore(path, legacy_path=None)
    settings = store.load()
    store.persist_session = False
    settings.scopes = ["/from-cli"]
    settings.pattern = "cli"
    settings.context_words = 3
    store.save(settings)
    reloaded = ConfigStore(path, legacy_path=None).load()
    assert reloaded.scopes == ["/saved"] and reloaded.pattern == "saved"
    assert reloaded.context_words == 3


def test_history_is_most_recent_first_and_bounded() -> None:
    settings = Settings()
    for i in range(HISTORY_LIMIT + 5):
        settings.remember_pattern(f"p{i}")
    settings.remember_pattern("p3")
    assert settings.history[0] == "p3"
    assert len(settings.history) == HISTORY_LIMIT
    assert settings.history.count("p3") == 1
