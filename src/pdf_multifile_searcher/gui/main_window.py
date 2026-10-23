# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""The main window: wires folder tree, search bar, result list and viewer together."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QGuiApplication,
    QKeySequence,
    QMoveEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdf_multifile_searcher import APP_NAME, system
from pdf_multifile_searcher.cache import TextCache, default_cache_path
from pdf_multifile_searcher.config import ConfigStore, Settings
from pdf_multifile_searcher.core.export import write_csv
from pdf_multifile_searcher.core.matcher import PatternError
from pdf_multifile_searcher.core.models import (
    FileMatches,
    Match,
    SearchOptions,
    SearchQuery,
    SearchSummary,
    SkippedFile,
)
from pdf_multifile_searcher.core.runner import SearchRunner
from pdf_multifile_searcher.gui.dialogs import PreferencesDialog, ProblemsDialog, show_about
from pdf_multifile_searcher.gui.folder_tree import FolderTree
from pdf_multifile_searcher.gui.icons import icon
from pdf_multifile_searcher.gui.results import (
    COL_CONTEXT,
    COL_FILE,
    MATCH_ROLE,
    PATH_ROLE,
    SORTABLE,
    ResultsModel,
    ResultsView,
)
from pdf_multifile_searcher.gui.search_thread import SearchThread
from pdf_multifile_searcher.gui.style import apply_theme, current_theme
from pdf_multifile_searcher.gui.viewer import PdfViewer
from pdf_multifile_searcher.pdf_backend import BACKEND_ID

log = logging.getLogger(__name__)

SAVE_DELAY_MS = 400


class MainWindow(QMainWindow):
    def __init__(
        self,
        store: ConfigStore,
        settings: Settings,
        *,
        cli_scopes: list[str] | None = None,
        cli_pattern: str | None = None,
        cli_options: SearchOptions | None = None,
        autostart: bool = False,
    ) -> None:
        super().__init__()
        self._store = store
        self.settings = settings
        self._thread: SearchThread | None = None
        self._old_threads: list[SearchThread] = []
        self._skipped: list[SkippedFile] = []
        self._last_pattern = ""
        self._restoring = True

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon("app"))
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_settings)

        self._build_ui()
        self._build_actions()
        self._apply_settings(cli_scopes, cli_pattern, cli_options)
        self._restoring = False
        self._prune_cache_later()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)
        if autostart:
            QTimer.singleShot(0, self.start_search)

    # ===================================================================================
    # UI construction
    # ===================================================================================

    def _tool_button(self, icon_name: str, tip: str, slot: Any) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(icon(icon_name))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def _build_ui(self) -> None:
        # -- search folders ----------------------------------------------------------------
        folders_panel = QWidget(self)
        folders_layout = QVBoxLayout(folders_panel)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel("Search folders", folders_panel)
        title.setObjectName("sectionTitle")
        header.addWidget(title, 1)
        header.addWidget(
            self._tool_button("folder-plus", "Add search folder…", self.add_search_folder)
        )
        header.addWidget(self._tool_button("file-plus", "Add PDF files…", self.add_search_files))
        header.addWidget(
            self._tool_button(
                "minus", "Remove selected search folders (Del)", self._remove_selected_scopes
            )
        )
        header.addWidget(self._tool_button("refresh", "Refresh folders", self._refresh_folders))
        folders_layout.addLayout(header)
        self.folder_tree = FolderTree(folders_panel)
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setToolTip("Drop folders or PDF files here to add them.")
        folders_layout.addWidget(self.folder_tree, 1)

        # -- search bar ----------------------------------------------------------------------
        search_panel = QWidget(self)
        search_layout = QVBoxLayout(search_panel)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)
        search_row = QHBoxLayout()
        search_row.setSpacing(4)
        self.pattern_box = QComboBox(search_panel)
        self.pattern_box.setEditable(True)
        self.pattern_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.pattern_box.setMaxVisibleItems(20)
        self.pattern_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.pattern_box.setMinimumContentsLength(10)
        self.pattern_edit = QLineEdit(self.pattern_box)
        self.pattern_box.setLineEdit(self.pattern_edit)
        self.pattern_edit.setPlaceholderText("Search pattern")
        self.pattern_edit.setClearButtonEnabled(True)
        self.pattern_edit.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.pattern_edit.returnPressed.connect(self.start_search)
        self.pattern_edit.textEdited.connect(self._clear_pattern_message)
        search_row.addWidget(self.pattern_box, 1)

        self.case_button = self._option_button("Aa", "Match case")
        self.word_button = self._option_button("ab", "Match whole words only")
        word_font = self.word_button.font()
        word_font.setUnderline(True)
        self.word_button.setFont(word_font)
        self.regex_button = self._option_button(".*", "Use regular expression")
        for b in (self.case_button, self.word_button, self.regex_button):
            search_row.addWidget(b)

        self.search_button = QPushButton("Search", search_panel)
        self.search_button.setObjectName("primary")
        self.search_button.setIcon(icon("search", current_theme_accent_text()))
        self.search_button.clicked.connect(self._on_search_button)
        search_row.addWidget(self.search_button)
        search_layout.addLayout(search_row)

        self.pattern_message = QLabel("", search_panel)
        self.pattern_message.setObjectName("message")
        self.pattern_message.setWordWrap(True)
        self.pattern_message.hide()
        search_layout.addWidget(self.pattern_message)

        # -- results -------------------------------------------------------------------------
        results_header = QHBoxLayout()
        results_title = QLabel("Results", search_panel)
        results_title.setObjectName("sectionTitle")
        results_header.addWidget(results_title)
        self.summary_label = QLabel("", search_panel)
        self.summary_label.setObjectName("muted")
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)
        self.summary_label.linkActivated.connect(self._show_problems)
        results_header.addWidget(self.summary_label, 1, Qt.AlignmentFlag.AlignRight)
        self.export_button = self._tool_button(
            "export", "Export results as CSV…", self.export_results
        )
        self.export_button.setEnabled(False)
        results_header.addWidget(self.export_button)
        search_layout.addSpacing(4)
        search_layout.addLayout(results_header)

        self.results_model = ResultsModel(self)
        self.results_view = ResultsView(self.results_model, search_panel)
        self.results_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.results_view.customContextMenuRequested.connect(self._results_menu)
        self.results_view.match_activated.connect(self._on_result_activated)
        self.results_view.sort_changed.connect(self._on_sort_changed)
        self.results_view.header().sectionResized.connect(lambda *_: self.schedule_save())

        self.results_placeholder = QLabel(
            "Add search folders, type a pattern and press Enter.", search_panel
        )
        self.results_placeholder.setObjectName("placeholder")
        self.results_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_placeholder.setWordWrap(True)
        self.results_stack = QStackedWidget(search_panel)
        self.results_stack.addWidget(self.results_placeholder)
        self.results_stack.addWidget(self.results_view)
        search_layout.addWidget(self.results_stack, 1)

        # -- left pane -------------------------------------------------------------------------
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.left_splitter.addWidget(folders_panel)
        self.left_splitter.addWidget(search_panel)
        self.left_splitter.setChildrenCollapsible(False)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.splitterMoved.connect(lambda *_: self.schedule_save())
        left = QWidget(self)
        left.setObjectName("leftPanel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 8, 6, 8)
        left_layout.addWidget(self.left_splitter)
        left.setMinimumWidth(100)

        # -- viewer ----------------------------------------------------------------------------
        self.viewer = PdfViewer(self)
        self.viewer.setMinimumWidth(100)
        self.viewer.set_highlight_provider(self.results_model.matches_on_page)
        self.viewer.page_changed.connect(self._on_page_changed)
        self.viewer.document_closed.connect(self._on_document_closed)
        self.viewer.open_failed.connect(self._on_open_failed)
        self.viewer.view_mode_changed.connect(self._on_view_mode_changed)
        self.viewer.step_match.connect(self.step_match)
        self.viewer.open_external.connect(self._open_external)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(left)
        self.main_splitter.addWidget(self.viewer)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.splitterMoved.connect(lambda *_: self.schedule_save())
        self.setCentralWidget(self.main_splitter)

        # -- status bar ------------------------------------------------------------------------
        self.progress = QProgressBar(self)
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.progress.hide()
        self.status_label = QLabel("Ready", self)
        self.file_label = QLabel("", self)
        self.statusBar().addWidget(self.progress)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.file_label)
        self.statusBar().setSizeGripEnabled(False)

        # -- folder tree signals -------------------------------------------------------------
        self.folder_tree.scopes_changed.connect(self._on_scopes_changed)
        self.folder_tree.pdf_selected.connect(lambda path: self.viewer.open(path, 0, None))
        self.folder_tree.message.connect(self.show_message)

    def _option_button(self, text: str, tip: str) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName("option")
        button.setText(text)
        button.setToolTip(tip)
        button.setCheckable(True)
        button.toggled.connect(self._on_options_changed)
        return button

    def _build_actions(self) -> None:
        def action(
            text: str, slot: Any, shortcut: Any = None, icon_name: str | None = None
        ) -> QAction:
            act = QAction(text, self)
            if icon_name:
                act.setIcon(icon(icon_name))
            if shortcut is not None:
                if isinstance(shortcut, list):
                    act.setShortcuts(shortcut)
                else:
                    act.setShortcut(shortcut)
            act.triggered.connect(slot)
            self.addAction(act)
            return act

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(
            action("&Open PDF…", self.open_pdf, QKeySequence.StandardKey.Open, "open")
        )
        file_menu.addAction(
            action("&Add search folder…", self.add_search_folder, None, "folder-plus")
        )
        file_menu.addAction(action("Add PDF &files…", self.add_search_files, None, "file-plus"))
        file_menu.addAction(
            action("&Clear search folders", self.clear_search_folders, None, "trash")
        )
        file_menu.addSeparator()
        self.export_action = action("&Export results…", self.export_results, "Ctrl+E", "export")
        self.export_action.setEnabled(False)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(
            action(
                "&Preferences…",
                self.show_preferences,
                QKeySequence.StandardKey.Preferences,
                "settings",
            )
        )
        file_menu.addSeparator()
        file_menu.addAction(action("E&xit", self.close, QKeySequence.StandardKey.Quit))

        search_menu = self.menuBar().addMenu("&Search")
        search_menu.addAction(
            action("&Find…", self.focus_pattern, QKeySequence.StandardKey.Find, "search")
        )
        self.cancel_action = action("&Cancel search", self.cancel_search, "Esc", "stop")
        self.cancel_action.setEnabled(False)
        search_menu.addAction(self.cancel_action)
        search_menu.addSeparator()
        search_menu.addAction(
            action("&Next match", lambda: self.step_match(True), "F3", "chevron-down")
        )
        search_menu.addAction(
            action("&Previous match", lambda: self.step_match(False), "Shift+F3", "chevron-up")
        )

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(
            action(
                "&Next page",
                self.viewer.next_page,
                QKeySequence.StandardKey.MoveToNextPage,
                "chevron-right",
            )
        )
        view_menu.addAction(
            action(
                "&Previous page",
                self.viewer.previous_page,
                QKeySequence.StandardKey.MoveToPreviousPage,
                "chevron-left",
            )
        )
        view_menu.addSeparator()
        view_menu.addAction(
            action("Zoom &in", self.viewer.zoom_in, ["Ctrl++", "Ctrl+="], "zoom-in")
        )
        view_menu.addAction(action("Zoom &out", self.viewer.zoom_out, "Ctrl+-", "zoom-out"))
        view_menu.addAction(
            action("Fit &width", lambda: self.viewer.set_fit("width"), "Ctrl+1", "fit-width")
        )
        view_menu.addAction(
            action("Fit &page", lambda: self.viewer.set_fit("page"), "Ctrl+2", "fit-page")
        )
        view_menu.addSeparator()
        view_menu.addAction(
            action(
                "Open in &system PDF viewer",
                self.viewer._emit_open_external,
                "Ctrl+Shift+O",
                "external",
            )
        )

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(action("&About", lambda: show_about(self), None, "info"))

    # ===================================================================================
    # Settings
    # ===================================================================================

    def _apply_settings(
        self,
        cli_scopes: list[str] | None,
        cli_pattern: str | None,
        cli_options: SearchOptions | None,
    ) -> None:
        s = self.settings
        w = s.window
        self.resize(max(w.width, 400), max(w.height, 300))
        if w.x is not None and w.y is not None:
            self._move_on_screen(w.x, w.y)
        if w.maximized:
            self.setWindowState(Qt.WindowState.WindowMaximized)

        self.folder_tree.include_hidden = s.include_hidden
        self.folder_tree.set_scopes(cli_scopes if cli_scopes else s.scopes)

        self._set_history(s.history)
        self.pattern_box.setEditText(cli_pattern if cli_pattern is not None else s.pattern)
        options = cli_options or SearchOptions(s.case_sensitive, s.whole_word, s.regex)
        self.case_button.setChecked(options.case_sensitive)
        self.word_button.setChecked(options.whole_word)
        self.regex_button.setChecked(options.regex)

        self.viewer.set_view_mode(s.viewer_fit, s.viewer_zoom)
        header = self.results_view.header()
        header.resizeSection(COL_FILE, max(60, w.file_column_width))
        if s.sort_column in SORTABLE:
            order = (
                Qt.SortOrder.DescendingOrder if s.sort_descending else Qt.SortOrder.AscendingOrder
            )
            self.results_view.apply_sort(s.sort_column, order)

        self.main_splitter.setSizes([max(100, w.sash), max(100, w.width - w.sash)])
        if len(w.left_sizes) == 2 and all(v > 0 for v in w.left_sizes):
            self.left_splitter.setSizes(w.left_sizes)
        else:
            self.left_splitter.setSizes([210, 600])

    def _move_on_screen(self, x: int, y: int) -> None:
        """Restore the position, but never off-screen (FR-CFG-07)."""
        geometry = QRect(x, y, self.width(), self.height())
        screen = QGuiApplication.screenAt(geometry.center()) or QGuiApplication.screenAt(
            QPoint(x + 40, y + 20)
        )
        if screen is None:
            primary = QGuiApplication.primaryScreen()
            if primary is not None:
                available = primary.availableGeometry()
                geometry.moveCenter(available.center())
                x, y = geometry.x(), geometry.y()
        self.move(x, y)

    def _set_history(self, history: list[str]) -> None:
        text = self.pattern_box.currentText()
        self.pattern_box.blockSignals(True)
        self.pattern_box.clear()
        self.pattern_box.addItems(history)
        self.pattern_box.setEditText(text)
        self.pattern_box.blockSignals(False)

    def schedule_save(self) -> None:
        if not self._restoring:
            self._save_timer.start()

    def save_settings(self) -> None:
        """Collect the current state and write it atomically (FR-CFG-02, FR-CFG-04)."""
        self._save_timer.stop()
        s = self.settings
        w = s.window
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        frame = self.frameGeometry() if not self.isMaximized() else None
        w.width, w.height = geometry.width(), geometry.height()
        if frame is not None:
            w.x, w.y = frame.x(), frame.y()
        w.maximized = self.isMaximized()
        sizes = self.main_splitter.sizes()
        if sizes and sizes[0] > 0:
            w.sash = sizes[0]
        w.left_sizes = list(self.left_splitter.sizes())
        header = self.results_view.header()
        w.file_column_width = header.sectionSize(COL_FILE)
        w.context_column_width = header.sectionSize(COL_CONTEXT)
        s.scopes = self.folder_tree.scopes()
        s.case_sensitive = self.case_button.isChecked()
        s.whole_word = self.word_button.isChecked()
        s.regex = self.regex_button.isChecked()
        s.viewer_fit = self.viewer.fit_mode
        s.viewer_zoom = self.viewer.zoom
        self._store.save(s)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.schedule_save()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self.schedule_save()

    def closeEvent(self, event: QCloseEvent) -> None:
        for thread in [self._thread, *self._old_threads]:
            if thread is not None:
                thread.cancel()
        for thread in [self._thread, *self._old_threads]:
            if thread is not None:
                thread.wait(5000)
        self.viewer.close_document(emit=False)
        self.save_settings()
        super().closeEvent(event)

    def _on_color_scheme_changed(self, *_args: Any) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, current_theme())
        self.search_button.setIcon(icon("search", current_theme_accent_text()))
        self.viewer.update()

    def _prune_cache_later(self) -> None:
        """Remove cache entries of deleted files in the background (FR-CACHE-05)."""
        if not self.settings.use_cache:
            return
        roots = [s for s in self.folder_tree.scopes() if os.path.isdir(s)]

        def prune() -> None:
            cache = TextCache(default_cache_path(), BACKEND_ID)
            try:
                removed = cache.prune(roots)
                if removed:
                    log.info("Removed %d stale text cache entries", removed)
            finally:
                cache.close()

        threading.Thread(target=prune, name="cache-prune", daemon=True).start()

    # ===================================================================================
    # Search folders
    # ===================================================================================

    def add_search_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add search folder")
        if path:
            self.folder_tree.add_scope(path)

    def add_search_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add PDF files", "", "PDF files (*.pdf *.PDF)"
        )
        for path in paths:
            self.folder_tree.add_scope(path)

    def clear_search_folders(self) -> None:
        self.folder_tree.clear_scopes()

    def _remove_selected_scopes(self) -> None:
        self.folder_tree.remove_selected_scopes()

    def _refresh_folders(self) -> None:
        self.folder_tree.refresh()
        self.show_message("Search folders refreshed.")

    def _on_scopes_changed(self, _scopes: list[str]) -> None:
        self.schedule_save()

    # ===================================================================================
    # Search
    # ===================================================================================

    def focus_pattern(self) -> None:
        self.pattern_box.setFocus()
        self.pattern_edit.selectAll()

    def _options(self) -> SearchOptions:
        return SearchOptions(
            case_sensitive=self.case_button.isChecked(),
            whole_word=self.word_button.isChecked(),
            regex=self.regex_button.isChecked(),
        )

    def _on_options_changed(self, _checked: bool) -> None:
        self._clear_pattern_message()
        self.schedule_save()

    def _show_pattern_message(self, text: str) -> None:
        self.pattern_message.setText(text)
        self.pattern_message.show()
        self.pattern_box.setProperty("invalid", True)
        self._repolish(self.pattern_box)

    def _clear_pattern_message(self, *_args: Any) -> None:
        if self.pattern_message.isVisible():
            self.pattern_message.hide()
            self.pattern_box.setProperty("invalid", False)
            self._repolish(self.pattern_box)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _on_search_button(self) -> None:
        if self._thread is not None:
            self.cancel_search()
        else:
            self.start_search()

    def start_search(self) -> None:
        pattern = self.pattern_box.currentText()
        query = SearchQuery(pattern, self._options(), self.settings.context_words)
        scopes = self.folder_tree.scopes()
        try:
            runner = SearchRunner(
                scopes,
                query,
                include_hidden=self.settings.include_hidden,
                cache_path=default_cache_path() if self.settings.use_cache else None,
                in_process=False,
            )
        except PatternError as exc:
            # Empty pattern (FR-SRCH-10) or invalid regular expression (FR-SRCH-13).
            self._show_pattern_message(str(exc))
            return
        if not scopes:
            self._show_pattern_message("Add a search folder first (File → Add search folder).")
            return
        self._clear_pattern_message()
        self._stop_current_thread()

        self.settings.pattern = pattern
        self.settings.remember_pattern(pattern)
        self._set_history(self.settings.history)
        self.schedule_save()
        self._last_pattern = pattern

        # A new search replaces the previous results completely (FR-SRCH-11).
        self.results_model.clear()
        self._skipped = []
        self.viewer.refresh_highlights(clear_selection=True)
        self.results_placeholder.setText("Searching…")
        self.results_stack.setCurrentWidget(self.results_placeholder)
        self.summary_label.setText("")
        self._set_export_enabled(False)

        thread = SearchThread(runner)
        thread.started_files.connect(lambda total, t=thread: self._on_started(t, total))
        thread.progress.connect(lambda d, n, m, t=thread: self._on_progress(t, d, n, m))
        thread.file_found.connect(lambda r, t=thread: self._on_file_found(t, r))
        thread.skipped.connect(lambda s, t=thread: self._on_skipped(t, s))
        thread.finished_search.connect(lambda s, t=thread: self._on_finished(t, s))
        thread.failed.connect(lambda msg, t=thread: self._on_failed(t, msg))
        thread.finished.connect(lambda t=thread: self._forget_thread(t))
        self._thread = thread
        self._set_searching(True)
        self.status_label.setText("Collecting files…")
        thread.start()

    def cancel_search(self) -> None:
        if self._thread is not None:
            self._thread.cancel()
            self.status_label.setText("Cancelling…")
            self.cancel_action.setEnabled(False)

    def _stop_current_thread(self) -> None:
        if self._thread is not None:
            self._thread.cancel()
            self._old_threads.append(self._thread)
            self._thread = None
            self._set_searching(False)

    def _forget_thread(self, thread: SearchThread) -> None:
        if thread in self._old_threads:
            self._old_threads.remove(thread)
        thread.deleteLater()

    def _set_searching(self, searching: bool) -> None:
        self.cancel_action.setEnabled(searching)
        self.progress.setVisible(searching)
        if searching:
            self.progress.setRange(0, 0)
            self.search_button.setText("Cancel")
            self.search_button.setIcon(icon("stop", current_theme_accent_text()))
            self.search_button.setToolTip("Cancel the search (Esc)")
        else:
            self.search_button.setText("Search")
            self.search_button.setIcon(icon("search", current_theme_accent_text()))
            self.search_button.setToolTip("Search (Enter)")

    def _on_started(self, thread: SearchThread, total: int) -> None:
        if thread is not self._thread:
            return
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.status_label.setText(f"Searching {total} file{'s' if total != 1 else ''}…")

    def _on_progress(self, thread: SearchThread, done: int, total: int, matches: int) -> None:
        if thread is not self._thread:
            return
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status_label.setText(
            f"Searching… {done} / {total} files · {matches} match{'es' if matches != 1 else ''}"
        )

    def _on_file_found(self, thread: SearchThread, result: FileMatches) -> None:
        if thread is not self._thread:
            return
        index = self.results_model.add_file(result)
        self.results_view.expand(index)
        if self.results_stack.currentWidget() is not self.results_view:
            self.results_stack.setCurrentWidget(self.results_view)
        self._set_export_enabled(True)
        if self.viewer.path == result.path:
            self.viewer.refresh_highlights()

    def _on_skipped(self, thread: SearchThread, skipped: SkippedFile) -> None:
        if thread is self._thread:
            self._skipped.append(skipped)

    def _on_finished(self, thread: SearchThread, summary: SearchSummary) -> None:
        if thread is not self._thread:
            return
        self._thread = None
        self._old_threads.append(thread)
        self._set_searching(False)
        self.results_model.reapply_sort()
        text = self._summary_text(summary)
        self.summary_label.setText(text)
        plain = text.replace("<a href='skipped'>", "").replace("</a>", "")
        self.status_label.setText(plain + f" · {summary.seconds:.1f} s")
        if summary.matches == 0:
            # Empty state (FR-RES-15).
            self.results_placeholder.setText(f"No matches for “{self._last_pattern}”.")
            self.results_stack.setCurrentWidget(self.results_placeholder)
        self.viewer.refresh_highlights()

    def _on_failed(self, thread: SearchThread, message: str) -> None:
        if thread is not self._thread:
            return
        self._thread = None
        self._old_threads.append(thread)
        self._set_searching(False)
        self.status_label.setText("Search failed.")
        QMessageBox.warning(self, "Search failed", f"The search could not run.\n\n{message}")

    @staticmethod
    def _summary_text(summary: SearchSummary) -> str:
        """Summary line (FR-SRCH-12), with a link to the skipped files (FR-ERR-02)."""
        n, f = summary.matches, summary.files_with_matches
        parts = [
            f"{n} match{'es' if n != 1 else ''} in {f} file{'s' if f != 1 else ''}",
            f"{summary.files_searched} searched",
        ]
        if summary.skipped:
            parts.append(f"<a href='skipped'>{len(summary.skipped)} skipped</a>")
        if summary.cancelled:
            parts.append("cancelled")
        return " · ".join(parts)

    def _show_problems(self, _link: str = "") -> None:
        if self._skipped:
            ProblemsDialog(self._skipped, self).exec()

    def _on_sort_changed(self, column: int, descending: bool) -> None:
        self.settings.sort_column = column
        self.settings.sort_descending = descending
        self.schedule_save()

    def _set_export_enabled(self, enabled: bool) -> None:
        self.export_button.setEnabled(enabled)
        self.export_action.setEnabled(enabled)

    # ===================================================================================
    # Results and viewer
    # ===================================================================================

    def _on_result_activated(self, index: QModelIndex) -> None:
        path = index.data(PATH_ROLE)
        match = index.data(MATCH_ROLE)
        if not path or not isinstance(match, Match):
            return
        if index.internalId() == 0:
            # A file row opens the page of its first match (FR-RES-11).
            self.viewer.open(path, match.page_index, None)
        else:
            self.viewer.open(path, match.page_index, match)

    def step_match(self, forward: bool) -> None:
        if not self.results_view.step_match(forward):
            self.show_message(
                "No more matches." if self.results_model.rowCount() else "No results."
            )

    def _results_menu(self, pos: QPoint) -> None:
        index = self.results_view.indexAt(pos)
        if not index.isValid():
            return
        path = index.data(PATH_ROLE)
        match = index.data(MATCH_ROLE)
        page = match.page_number if isinstance(match, Match) else 1
        menu = QMenu(self)
        open_ext = menu.addAction(icon("external"), "Open in system PDF viewer")
        open_ext.triggered.connect(lambda: self._open_external(path, page))
        copy = menu.addAction(icon("copy"), "Copy path")
        copy.triggered.connect(lambda: QGuiApplication.clipboard().setText(path))
        show = menu.addAction("Show in file manager")
        show.triggered.connect(lambda: system.show_in_file_manager(path))
        menu.exec(self.results_view.viewport().mapToGlobal(pos))

    def _open_external(self, path: str, page_number: int) -> None:
        at_page = system.open_pdf_external(path, page_number)
        if page_number > 1 and not at_page:
            self.show_message(
                f"Opened {os.path.basename(path)} in the system viewer, which cannot be told "
                f"to start at page {page_number}."
            )

    def open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf *.PDF)")
        if path:
            self.viewer.open(path, 0, None)

    def _on_page_changed(self, path: str, page_index: int, page_count: int) -> None:
        name = os.path.basename(path)
        self.setWindowTitle(f"{name} — Page {page_index + 1} / {page_count} — {APP_NAME}")
        self.file_label.setText(path)
        self.file_label.setToolTip(path)

    def _on_document_closed(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.file_label.setText("")

    def _on_open_failed(self, message: str) -> None:
        self.show_message(message, 8000)

    def _on_view_mode_changed(self, _fit: str, _zoom: float) -> None:
        self.schedule_save()

    # ===================================================================================
    # Misc
    # ===================================================================================

    def show_message(self, text: str, timeout: int = 5000) -> None:
        self.statusBar().showMessage(text, timeout)

    def export_results(self) -> None:
        matches = self.results_model.all_matches()
        if not matches:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export results", "search-results.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        try:
            # UTF-8 with BOM so spreadsheet programs detect the encoding (FR-RES-13).
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                count = write_csv(matches, fh)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not write {path}:\n{exc}")
            return
        self.show_message(f"Exported {count} matches to {path}.")

    def show_preferences(self) -> None:
        cache = TextCache(default_cache_path(), BACKEND_ID)

        def clear() -> None:
            cache.clear()
            self.show_message("Text cache cleared.")

        dialog = PreferencesDialog(self.settings, cache.size_bytes, clear, self)
        try:
            if dialog.exec():
                hidden_changed = dialog.include_hidden.isChecked() != self.settings.include_hidden
                dialog.apply_to(self.settings)
                if hidden_changed:
                    self.folder_tree.include_hidden = self.settings.include_hidden
                    self.folder_tree.refresh()
                self.save_settings()
        finally:
            cache.close()


def current_theme_accent_text() -> QColor:
    return QColor(current_theme().accent_text)
