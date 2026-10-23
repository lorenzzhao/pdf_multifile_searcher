"""Result list: a two-level model (files → matches), its view and delegate (FR-RES)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from pdf_multifile_searcher.core.models import FileMatches, Match
from pdf_multifile_searcher.gui.icons import PDF_COLOR, icon

COL_FILE, COL_CONTEXT, COL_PAGE, COL_ID = range(4)
HEADERS = ("File", "Context", "Page", "ID")
SORTABLE = (COL_FILE, COL_PAGE, COL_ID)  # Context is not sortable (FR-RES-07)

MATCH_ROLE = Qt.ItemDataRole.UserRole + 10
PATH_ROLE = Qt.ItemDataRole.UserRole + 11

_ModelIndex = QModelIndex | QPersistentModelIndex


@dataclass
class _FileEntry:
    path: str
    matches: list[Match] = field(default_factory=list)


class ResultsModel(QAbstractItemModel):
    """Files are top-level rows (internal id 0); a match row's internal id is its file's
    row + 1."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[_FileEntry] = []
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._pdf_icon = icon("file-pdf", PDF_COLOR)

    # -- content -------------------------------------------------------------------------

    def clear(self) -> None:
        self.beginResetModel()
        self._files = []
        self.endResetModel()

    def add_file(self, result: FileMatches) -> QModelIndex:
        row = len(self._files)
        self.beginInsertRows(QModelIndex(), row, row)
        self._files.append(_FileEntry(result.path, list(result.matches)))
        self.endInsertRows()
        return self.index(row, 0)

    def match_count(self) -> int:
        return sum(len(f.matches) for f in self._files)

    def all_matches(self) -> list[Match]:
        """All matches in display order."""
        return [m for f in self._files for m in f.matches]

    def matches_on_page(self, path: str, page_index: int) -> list[Match]:
        for entry in self._files:
            if entry.path == path:
                return [m for m in entry.matches if m.page_index == page_index]
        return []

    def index_of_match(self, match_id: int) -> QModelIndex:
        for file_row, entry in enumerate(self._files):
            for match_row, m in enumerate(entry.matches):
                if m.match_id == match_id:
                    return self.index(match_row, 0, self.index(file_row, 0))
        return QModelIndex()

    # -- sorting (FR-RES-07, FR-RES-08) --------------------------------------------------

    @property
    def sort_column(self) -> int:
        return self._sort_column

    @property
    def sort_order(self) -> Qt.SortOrder:
        return self._sort_order

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if column not in SORTABLE:
            return
        self._sort_column = column
        self._sort_order = order
        self._apply_sort()

    def reapply_sort(self) -> None:
        if self._sort_column in SORTABLE:
            self._apply_sort()

    def _apply_sort(self) -> None:
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        old = self.persistentIndexList()
        old_keys = [self._key_for(i) for i in old]
        if self._sort_column == COL_FILE:
            self._files.sort(key=lambda f: f.path.casefold(), reverse=reverse)
            for entry in self._files:
                entry.matches.sort(key=lambda m: m.match_id)
        else:
            if self._sort_column == COL_PAGE:

                def key(m: Match) -> tuple[int, int]:
                    return (m.page_index, m.match_id)
            else:

                def key(m: Match) -> tuple[int, int]:
                    return (m.match_id, 0)

            for entry in self._files:
                entry.matches.sort(key=key, reverse=reverse)
            # Files follow the order of their first match.
            self._files.sort(
                key=lambda f: key(f.matches[0]) if f.matches else (0, 0), reverse=reverse
            )
        new = [self._index_for_key(k, i.column()) for k, i in zip(old_keys, old, strict=True)]
        self.changePersistentIndexList(old, new)
        self.layoutChanged.emit()

    def _key_for(self, index: QModelIndex) -> tuple[str, int]:
        if not index.isValid():
            return ("", -1)
        if index.internalId() == 0:
            return (self._files[index.row()].path, -1)
        entry = self._files[index.internalId() - 1]
        return (entry.path, entry.matches[index.row()].match_id)

    def _index_for_key(self, key: tuple[str, int], column: int) -> QModelIndex:
        path, match_id = key
        for file_row, entry in enumerate(self._files):
            if entry.path != path:
                continue
            if match_id < 0:
                return self.index(file_row, column)
            for match_row, m in enumerate(entry.matches):
                if m.match_id == match_id:
                    return self.index(match_row, column, self.index(file_row, 0))
        return QModelIndex()

    # -- Qt model interface --------------------------------------------------------------

    def index(self, row: int, column: int, parent: _ModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, index: _ModelIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]
        if not index.isValid() or index.internalId() == 0:
            return QModelIndex()
        return self.createIndex(index.internalId() - 1, 0, 0)

    def rowCount(self, parent: _ModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._files)
        if parent.internalId() == 0 and parent.column() == 0:
            return len(self._files[parent.row()].matches)
        return 0

    def columnCount(self, parent: _ModelIndex = QModelIndex()) -> int:
        return len(HEADERS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return HEADERS[section]
            if role == Qt.ItemDataRole.TextAlignmentRole and section in (COL_PAGE, COL_ID):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index: _ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        column = index.column()
        if index.internalId() == 0:
            entry = self._files[index.row()]
            if role == PATH_ROLE:
                return entry.path
            if role == MATCH_ROLE:
                return entry.matches[0] if entry.matches else None
            if column == COL_FILE:
                if role == Qt.ItemDataRole.DisplayRole:
                    return entry.path
                if role == Qt.ItemDataRole.ToolTipRole:
                    return entry.path  # full path (FR-RES-06)
                if role == Qt.ItemDataRole.DecorationRole:
                    return self._pdf_icon
            if column == COL_CONTEXT and role == Qt.ItemDataRole.DisplayRole:
                n = len(entry.matches)
                return f"{n} match{'es' if n != 1 else ''}"
            return None
        entry = self._files[index.internalId() - 1]
        match = entry.matches[index.row()]
        if role == MATCH_ROLE:
            return match
        if role == PATH_ROLE:
            return entry.path
        if role == Qt.ItemDataRole.DisplayRole:
            if column == COL_CONTEXT:
                return match.context
            if column == COL_PAGE:
                return str(match.page_number)  # 1-based (FR-RES-03)
            if column == COL_ID:
                return str(match.match_id)
        if role == Qt.ItemDataRole.ToolTipRole and column == COL_CONTEXT:
            return match.context
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (COL_PAGE, COL_ID):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def flags(self, index: _ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable


class ContextDelegate(QStyledItemDelegate):
    """Draws the context with the matched text in bold (FR-MATCH-05), keeping the match
    visible when the column is narrow."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: _ModelIndex) -> None:
        match = index.data(MATCH_ROLE)
        if index.internalId() == 0 or not isinstance(match, Match):
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            opt.palette.setColor(
                QPalette.ColorRole.Text, opt.palette.color(QPalette.ColorRole.PlaceholderText)
            )
            super().paint(painter, opt, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        rect: QRect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, opt, opt.widget)
        rect = rect.adjusted(4, 0, -4, 0)
        start, end = match.page.context_match_start, match.page.context_match_end
        before, hit, after = text[:start], text[start:end], text[end:]
        normal_font = QFont(opt.font)
        bold_font = QFont(opt.font)
        bold_font.setBold(True)
        fm, bfm = QFontMetrics(normal_font), QFontMetrics(bold_font)
        available = rect.width()
        hit_w = min(bfm.horizontalAdvance(hit) + 1, available)
        remaining = max(0, available - hit_w)
        before_w, after_w = fm.horizontalAdvance(before), fm.horizontalAdvance(after)
        if before_w + after_w > remaining:
            before_alloc = min(before_w, max(remaining // 3, remaining - after_w))
        else:
            before_alloc = before_w
        after_alloc = remaining - before_alloc
        before_txt = (
            fm.elidedText(before, Qt.TextElideMode.ElideLeft, before_alloc) if before else ""
        )
        hit_txt = (
            hit if hit_w < available else bfm.elidedText(hit, Qt.TextElideMode.ElideRight, hit_w)
        )
        after_txt = fm.elidedText(after, Qt.TextElideMode.ElideRight, after_alloc) if after else ""

        color = opt.palette.color(QPalette.ColorRole.Text)
        painter.save()
        painter.setPen(color)
        x = rect.left()
        flags = int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        for segment, font, metrics in (
            (before_txt, normal_font, fm),
            (hit_txt, bold_font, bfm),
            (after_txt, normal_font, fm),
        ):
            if not segment:
                continue
            painter.setFont(font)
            width = metrics.horizontalAdvance(segment)
            painter.drawText(QRect(x, rect.top(), width + 1, rect.height()), flags, segment)
            x += width
        painter.restore()


class ResultsView(QTreeView):
    """The result tree with click-to-sort headers and match navigation."""

    match_activated = Signal(object)  # Match, or None
    sort_changed = Signal(int, bool)  # column, descending

    def __init__(self, model: ResultsModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModel(model)
        self._model = model
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)  # paths shortened in the middle
        self.setItemDelegateForColumn(COL_CONTEXT, ContextDelegate(self))
        self.setAllColumnsShowFocus(True)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_CONTEXT, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_PAGE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ID, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(COL_PAGE, 52)
        header.resizeSection(COL_ID, 52)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(False)
        header.sectionClicked.connect(self._on_header_clicked)
        self.selectionModel().currentChanged.connect(self._on_current_changed)

    # -- sorting -------------------------------------------------------------------------

    def _on_header_clicked(self, section: int) -> None:
        if section not in SORTABLE:
            self._show_indicator()
            return
        if self._model.sort_column == section:
            order = (
                Qt.SortOrder.DescendingOrder
                if self._model.sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            order = Qt.SortOrder.AscendingOrder
        self.apply_sort(section, order)
        self.sort_changed.emit(section, order == Qt.SortOrder.DescendingOrder)

    def apply_sort(self, column: int, order: Qt.SortOrder) -> None:
        self._model.sort(column, order)
        self._show_indicator()
        current = self.currentIndex()
        if current.isValid():
            self.scrollTo(current)

    def _show_indicator(self) -> None:
        header = self.header()
        if self._model.sort_column in SORTABLE:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(self._model.sort_column, self._model.sort_order)
        else:
            header.setSortIndicatorShown(False)

    # -- selection and navigation --------------------------------------------------------

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        self.match_activated.emit(current)

    def step_match(self, forward: bool) -> bool:
        """Select the next or previous match, crossing file boundaries (FR-RES-12)."""
        model = self._model
        files = model.rowCount()
        if files == 0:
            return False
        current = self.currentIndex()
        if not current.isValid():
            file_row, match_row = (0, -1) if forward else (files - 1, None)
        elif current.internalId() == 0:
            file_row = current.row()
            match_row = -1 if forward else 0
        else:
            file_row, match_row = current.internalId() - 1, current.row()
        while 0 <= file_row < files:
            count = model.rowCount(model.index(file_row, 0))
            if match_row is None:
                match_row = count
            target = match_row + (1 if forward else -1)
            if 0 <= target < count:
                index = model.index(target, 0, model.index(file_row, 0))
                self.setCurrentIndex(index)
                self.scrollTo(index)
                return True
            file_row += 1 if forward else -1
            match_row = -1 if forward else None
        return False
