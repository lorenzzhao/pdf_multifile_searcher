"""The "Search folders" tree (FR-SCOPE, FR-TREE)."""

from __future__ import annotations

import os

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QPalette,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import QAbstractItemView, QMenu, QTreeView, QWidget

from pdf_multifile_searcher import system
from pdf_multifile_searcher.core.scopes import (
    is_hidden_name,
    is_pdf_name,
    normalize_scope,
    same_scope,
)
from pdf_multifile_searcher.gui.icons import FOLDER_COLOR, PDF_COLOR, WARNING_COLOR, icon

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2
LOADED_ROLE = Qt.ItemDataRole.UserRole + 3

KIND_FOLDER = "folder"
KIND_PDF = "pdf"
KIND_PLACEHOLDER = "placeholder"


class FolderTree(QTreeView):
    """Shows the registered search scopes with lazily loaded children."""

    scopes_changed = Signal(list)
    pdf_selected = Signal(str)
    message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(["Search folders"])
        self.setModel(self._model)
        self.include_hidden = False
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.expanded.connect(self._on_expanded)
        self.customContextMenuRequested.connect(self._show_menu)
        self.selectionModel().currentChanged.connect(self._on_current_changed)
        self._folder_icon = icon("folder", FOLDER_COLOR)
        self._pdf_icon = icon("file-pdf", PDF_COLOR)
        self._warning_icon = icon("warning", WARNING_COLOR)

    # -- scopes --------------------------------------------------------------------------

    def scopes(self) -> list[str]:
        root = self._model.invisibleRootItem()
        return [root.child(i).data(PATH_ROLE) for i in range(root.rowCount())]

    def set_scopes(self, scopes: list[str]) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for scope in scopes:
            self._append_scope(scope)

    def add_scope(self, path: str) -> bool:
        """Register a folder or PDF file. Refuses duplicates (FR-SCOPE-06)."""
        path = normalize_scope(path)
        for existing in self.scopes():
            if same_scope(existing, path):
                self.message.emit(f"Already in search folders: {path}")
                return False
        if os.path.isfile(path) and not is_pdf_name(path):
            self.message.emit(f"Not a PDF file: {path}")
            return False
        self._append_scope(path)
        self.scopes_changed.emit(self.scopes())
        return True

    def remove_selected_scopes(self) -> None:
        """Remove selected top-level nodes; other nodes are ignored (FR-SCOPE-04)."""
        rows = sorted(
            {i.row() for i in self.selectionModel().selectedRows() if not i.parent().isValid()},
            reverse=True,
        )
        if not rows:
            return
        for row in rows:
            self._model.removeRow(row)
        self.scopes_changed.emit(self.scopes())

    def clear_scopes(self) -> None:
        if self._model.rowCount():
            self._model.removeRows(0, self._model.rowCount())
            self.scopes_changed.emit([])

    def refresh(self) -> None:
        """Rescan all scopes from disk (FR-TREE-08)."""
        self.set_scopes(self.scopes())

    def _append_scope(self, path: str) -> None:
        item = QStandardItem(path)
        item.setData(path, PATH_ROLE)
        item.setToolTip(path)
        if os.path.isdir(path):
            item.setData(KIND_FOLDER, KIND_ROLE)
            item.setIcon(self._folder_icon)
            self._add_placeholder(item)
        elif os.path.isfile(path):
            item.setData(KIND_PDF, KIND_ROLE)
            item.setIcon(self._pdf_icon)
        else:
            # Unavailable, for example on an unmounted drive (FR-SCOPE-07).
            item.setData(KIND_FOLDER, KIND_ROLE)
            item.setIcon(self._warning_icon)
            item.setText(f"{path}  (not available)")
            item.setToolTip(f"{path}\nThis folder is not available and will be skipped.")
            item.setForeground(
                self.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
            )
        self._model.appendRow(item)

    # -- lazy loading (FR-TREE-04) -------------------------------------------------------

    def _add_placeholder(self, item: QStandardItem) -> None:
        placeholder = QStandardItem("Loading…")
        placeholder.setData(KIND_PLACEHOLDER, KIND_ROLE)
        placeholder.setForeground(QColor(self.palette().color(QPalette.ColorRole.PlaceholderText)))
        placeholder.setSelectable(False)
        item.appendRow(placeholder)
        item.setData(False, LOADED_ROLE)

    def _on_expanded(self, index: QModelIndex) -> None:
        item = self._model.itemFromIndex(index)
        if item is None or item.data(LOADED_ROLE) is not False:
            return
        item.setData(True, LOADED_ROLE)
        item.removeRows(0, item.rowCount())
        path = item.data(PATH_ROLE)
        try:
            with os.scandir(path) as it:
                entries = list(it)
        except OSError as exc:
            error = QStandardItem(f"Cannot read folder: {exc.strerror or exc}")
            error.setIcon(self._warning_icon)
            error.setSelectable(False)
            item.appendRow(error)
            return
        folders: list[os.DirEntry[str]] = []
        pdfs: list[os.DirEntry[str]] = []
        for entry in entries:
            # The tree and the search apply the same hidden-file rule (FR-TREE-06).
            if not self.include_hidden and is_hidden_name(entry.name):
                continue
            try:
                if entry.is_dir():
                    folders.append(entry)
                elif entry.is_file() and is_pdf_name(entry.name):
                    pdfs.append(entry)
            except OSError:
                continue
        for entry in sorted(folders, key=lambda e: e.name.casefold()):
            child = QStandardItem(self._folder_icon, entry.name)
            child.setData(entry.path, PATH_ROLE)
            child.setData(KIND_FOLDER, KIND_ROLE)
            child.setToolTip(entry.path)
            self._add_placeholder(child)
            item.appendRow(child)
        for entry in sorted(pdfs, key=lambda e: e.name.casefold()):
            child = QStandardItem(self._pdf_icon, entry.name)
            child.setData(entry.path, PATH_ROLE)
            child.setData(KIND_PDF, KIND_ROLE)
            child.setToolTip(entry.path)
            item.appendRow(child)

    # -- interaction ---------------------------------------------------------------------

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if current.isValid() and current.data(KIND_ROLE) == KIND_PDF:
            self.pdf_selected.emit(current.data(PATH_ROLE))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self.remove_selected_scopes()
            return
        super().keyPressEvent(event)

    def _show_menu(self, pos: QPoint) -> None:
        index = self.indexAt(pos)
        menu = QMenu(self)
        if index.isValid():
            path = index.data(PATH_ROLE)
            kind = index.data(KIND_ROLE)
            if kind == KIND_PDF and path:
                open_action = QAction(icon("external"), "Open in system PDF viewer", menu)
                open_action.triggered.connect(lambda: system.open_pdf_external(path))
                menu.addAction(open_action)
            if path and kind != KIND_PLACEHOLDER:
                show = QAction("Show in file manager", menu)
                show.triggered.connect(lambda: system.show_in_file_manager(path))
                menu.addAction(show)
            if not index.parent().isValid():
                if not menu.isEmpty():
                    menu.addSeparator()
                remove = QAction(icon("minus"), "Remove from search folders", menu)
                remove.setShortcut(Qt.Key.Key_Delete)
                remove.triggered.connect(self.remove_selected_scopes)
                menu.addAction(remove)
            menu.addSeparator()
        refresh = QAction(icon("refresh"), "Refresh", menu)
        refresh.triggered.connect(self.refresh)
        menu.addAction(refresh)
        menu.exec(self.viewport().mapToGlobal(pos))

    # -- drag and drop (FR-SCOPE-02, FR-SCOPE-03) ----------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        added = 0
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if os.path.isdir(path) or (os.path.isfile(path) and is_pdf_name(path)):
                added += self.add_scope(path)
            else:
                self.message.emit(f"Only folders and PDF files can be added: {path}")
        event.acceptProposedAction()
        if added:
            self.message.emit(f"Added {added} search scope{'s' if added != 1 else ''}.")
