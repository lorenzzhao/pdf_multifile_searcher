# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""End-to-end GUI tests on the offscreen platform (pytest-qt)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from pdf_multifile_searcher.config import ConfigStore, Settings
from pdf_multifile_searcher.core.models import Match
from pdf_multifile_searcher.gui.main_window import MainWindow
from pdf_multifile_searcher.gui.results import COL_PAGE, MATCH_ROLE


@pytest.fixture
def window(qtbot, tmp_path: Path, data_dir: Path):
    store = ConfigStore(tmp_path / "settings.json", legacy_path=None)
    settings = Settings(scopes=[str(data_dir)], use_cache=False)
    win = MainWindow(store, settings)
    qtbot.addWidget(win)
    win.resize(1300, 800)
    win.show()
    return win


def run_search(qtbot, win: MainWindow, pattern: str) -> None:
    win.pattern_box.setEditText(pattern)
    win.start_search()
    qtbot.waitUntil(lambda: win._thread is None, timeout=30000)


def test_search_fills_results_and_summary(qtbot, window: MainWindow) -> None:
    run_search(qtbot, window, "Zephyria")
    assert window.results_model.match_count() == 4
    assert window.summary_label.text().startswith("4 matches in 1 file")
    assert window.results_stack.currentWidget() is window.results_view
    assert window.settings.history[0] == "Zephyria"


def test_empty_pattern_shows_hint(qtbot, window: MainWindow) -> None:
    window.pattern_box.setEditText("  ")
    window.start_search()
    assert window._thread is None
    assert not window.pattern_message.isHidden()


def test_invalid_regex_shows_message(qtbot, window: MainWindow) -> None:
    window.regex_button.setChecked(True)
    window.pattern_box.setEditText("(")
    window.start_search()
    assert "Invalid regular expression" in window.pattern_message.text()


def test_no_matches_empty_state(qtbot, window: MainWindow) -> None:
    run_search(qtbot, window, "xyzzy-nothing")
    assert window.results_stack.currentWidget() is window.results_placeholder
    assert "No matches" in window.results_placeholder.text()


def test_selecting_a_match_opens_its_page(qtbot, window: MainWindow) -> None:
    run_search(qtbot, window, "magic")
    assert window.results_view.step_match(True)
    assert window.results_view.step_match(True)
    match = window.results_view.currentIndex().data(MATCH_ROLE)
    assert isinstance(match, Match)
    assert window.viewer.path == match.path
    assert window.viewer.page_index == match.page_index
    assert f"Page {match.page_number} /" in window.windowTitle()
    # Previous match crosses back into the first file.
    assert window.results_view.step_match(False)
    assert window.viewer.path != match.path


def test_sort_by_page_descending(qtbot, window: MainWindow) -> None:
    run_search(qtbot, window, "the")
    view = window.results_view
    view._on_header_clicked(COL_PAGE)
    view._on_header_clicked(COL_PAGE)
    model = window.results_model
    assert model.sort_order == Qt.SortOrder.DescendingOrder
    first_file = model.index(0, 0)
    pages = [
        model.index(r, 0, first_file).data(MATCH_ROLE).page_index
        for r in range(model.rowCount(first_file))
    ]
    assert pages == sorted(pages, reverse=True)
    assert window.settings.sort_column == COL_PAGE


def test_new_search_clears_highlights(qtbot, window: MainWindow) -> None:
    run_search(qtbot, window, "magic")
    window.results_view.step_match(True)
    path, page = window.viewer.path, window.viewer.page_index
    assert path is not None
    assert window.results_model.matches_on_page(path, page)
    run_search(qtbot, window, "xyzzy-nothing")
    assert window.results_model.matches_on_page(path, page) == []


def test_duplicate_scope_refused(qtbot, window: MainWindow, data_dir: Path) -> None:
    assert not window.folder_tree.add_scope(str(data_dir))
    assert window.folder_tree.scopes() == [str(data_dir)]


def test_export_csv(qtbot, window: MainWindow, tmp_path: Path, monkeypatch) -> None:
    run_search(qtbot, window, "lorem ipsum")
    target = tmp_path / "out.csv"
    monkeypatch.setattr(
        "pdf_multifile_searcher.gui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), ""),
    )
    window.export_results()
    with target.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["file", "page", "context", "id"] and len(rows) == 3


def test_settings_saved_on_close(qtbot, window: MainWindow, tmp_path: Path) -> None:
    window.folder_tree.add_scope(str(tmp_path))
    window.close()
    saved = ConfigStore(tmp_path / "settings.json", legacy_path=None).load()
    assert str(tmp_path) in saved.scopes
