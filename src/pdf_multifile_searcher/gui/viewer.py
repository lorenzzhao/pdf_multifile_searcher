# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""The PDF viewer pane (FR-VIEW) with match highlighting (FR-HL)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QIntValidator,
    QPainter,
    QPaintEvent,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pdf_multifile_searcher.core.models import Match
from pdf_multifile_searcher.gui.icons import icon
from pdf_multifile_searcher.gui.style import current_theme
from pdf_multifile_searcher.pdf_backend import PdfDocumentHandle, PdfOpenError, Rect, open_document

MARGIN = 16
POINTS_TO_PX = 96 / 72  # 100 % zoom shows the page at its physical size on a 96-dpi screen
ZOOM_STEPS = (0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0)
FIT_WIDTH, FIT_PAGE, FIT_CUSTOM = "width", "page", "custom"

KIND_MATCH, KIND_SELECTED, KIND_CONTEXT = range(3)


@dataclass(frozen=True)
class _Mark:
    kind: int
    rect: QRectF  # in logical pixels relative to the page's top-left corner


class PageCanvas(QWidget):
    """Paints the rendered page and the highlight marks."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: QImage | None = None
        self._page_size = QSize(0, 0)
        self._marks: list[_Mark] = []
        self._message = ""
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_page(self, image: QImage, logical_size: QSize, marks: list[_Mark]) -> None:
        self._image = image
        self._page_size = logical_size
        self._marks = marks
        self._message = ""
        self.resize(logical_size.width() + 2 * MARGIN, logical_size.height() + 2 * MARGIN)
        self.update()

    def set_marks(self, marks: list[_Mark]) -> None:
        self._marks = marks
        self.update()

    def set_message(self, message: str, size: QSize) -> None:
        self._image = None
        self._marks = []
        self._message = message
        self.resize(size)
        self.update()

    def page_origin(self) -> QPointF:
        return QPointF(MARGIN, MARGIN)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = current_theme()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.viewer_bg))
        if self._image is None:
            painter.setPen(QColor(theme.muted))
            painter.drawText(
                self.rect().adjusted(24, 24, -24, -24),
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._message,
            )
            return
        page_rect = QRectF(self.page_origin(), self._page_size.toSizeF())
        # Soft shadow below the page.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, alpha in enumerate((28, 18, 10)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(page_rect.adjusted(-i, -i + 1, i, i + 2), 2 + i, 2 + i)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(page_rect, self._image)
        self._paint_marks(painter)

    def _paint_marks(self, painter: QPainter) -> None:
        t = current_theme()
        origin = self.page_origin()
        styles = {
            KIND_CONTEXT: (QColor(t.context_line), 1.0, Qt.PenStyle.DashLine, QColor(0, 0, 0, 0)),
            KIND_MATCH: (QColor(t.match_line), 1.0, Qt.PenStyle.SolidLine, QColor(t.match_fill)),
            KIND_SELECTED: (
                QColor(t.selected_line),
                2.5,
                Qt.PenStyle.SolidLine,
                QColor(t.selected_fill),
            ),
        }
        # Draw context first, then other matches, then the selected match on top.
        for kind in (KIND_CONTEXT, KIND_MATCH, KIND_SELECTED):
            line, width, pen_style, fill = styles[kind]
            pen = QPen(line, width, pen_style)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QBrush(fill))
            for mark in self._marks:
                if mark.kind == kind:
                    pad = 2.0 if kind == KIND_CONTEXT else 1.0
                    r = mark.rect.translated(origin).adjusted(-pad, -pad, pad, pad)
                    painter.drawRoundedRect(r, 2, 2)


class _WheelZoomFilter(QObject):
    def __init__(self, viewer: PdfViewer) -> None:
        super().__init__(viewer)
        self._viewer = viewer

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.Wheel
            and isinstance(event, QWheelEvent)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if event.angleDelta().y() > 0:
                self._viewer.zoom_in()
            elif event.angleDelta().y() < 0:
                self._viewer.zoom_out()
            return True
        if event.type() == QEvent.Type.Resize:
            self._viewer.schedule_relayout()
        return False


HighlightProvider = Callable[[str, int], list[Match]]


class PdfViewer(QWidget):
    """Shows one page of one document at a time."""

    page_changed = Signal(str, int, int)  # path, 0-based page, page count
    document_closed = Signal()
    open_failed = Signal(str)
    view_mode_changed = Signal(str, float)  # fit mode, zoom
    step_match = Signal(bool)  # True = next match
    open_external = Signal(str, int)  # path, 1-based page

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: PdfDocumentHandle | None = None
        self._path: str | None = None
        self._page = 0
        self._fit = FIT_WIDTH
        self._zoom = 1.0
        self._selected: Match | None = None
        self._rect_cache: dict[tuple[str, int, int, int], list[Rect]] = {}
        self._provider: HighlightProvider = lambda _path, _page: []
        self._scroll_to_selected = False

        self._build_ui()
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(60)
        self._relayout_timer.timeout.connect(self._render)
        self._show_empty()

    # -- UI ------------------------------------------------------------------------------

    def _tool(
        self, icon_name: str, tip: str, slot: Callable[[], object], checkable: bool = False
    ) -> QToolButton:
        button = QToolButton(self)
        button.setIcon(icon(icon_name))
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setCheckable(checkable)
        button.clicked.connect(slot)
        return button

    def _separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(10)
        line.setStyleSheet("color: transparent;")
        return line

    def _build_ui(self) -> None:
        bar = QWidget(self)
        bar.setObjectName("viewerToolbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(2)

        self._title = QLabel("", bar)
        self._title.setObjectName("sectionTitle")
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self._title, 1)

        self._prev_page = self._tool("chevron-left", "Previous page (PgUp)", self.previous_page)
        # Jump to a page by typing its number (FR-VIEW-06).
        self._page_spin = QLineEdit(bar)
        self._page_validator = QIntValidator(1, 1, self._page_spin)
        self._page_spin.setValidator(self._page_validator)
        self._page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_spin.setToolTip("Type a page number and press Enter")
        self._page_spin.setFixedWidth(52)
        self._page_spin.editingFinished.connect(self._on_page_entered)
        self._page_count = QLabel("/ 0", bar)
        self._page_count.setObjectName("muted")
        self._next_page = self._tool("chevron-right", "Next page (PgDown)", self.next_page)
        for w in (self._prev_page, self._page_spin, self._page_count, self._next_page):
            row.addWidget(w)
        row.addWidget(self._separator())

        self._zoom_out = self._tool("zoom-out", "Zoom out (Ctrl+−)", self.zoom_out)
        self._zoom_label = QLabel("100 %", bar)
        self._zoom_label.setObjectName("muted")
        self._zoom_label.setFixedWidth(48)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_in = self._tool("zoom-in", "Zoom in (Ctrl++)", self.zoom_in)
        self._fit_width = self._tool(
            "fit-width", "Fit width", lambda: self.set_fit(FIT_WIDTH), checkable=True
        )
        self._fit_page = self._tool(
            "fit-page", "Fit whole page", lambda: self.set_fit(FIT_PAGE), checkable=True
        )
        for w in (self._zoom_out, self._zoom_label, self._zoom_in, self._fit_width, self._fit_page):
            row.addWidget(w)
        row.addWidget(self._separator())

        self._prev_match = self._tool(
            "chevron-up", "Previous match (Shift+F3)", lambda: self.step_match.emit(False)
        )
        self._next_match = self._tool(
            "chevron-down", "Next match (F3)", lambda: self.step_match.emit(True)
        )
        self._external = self._tool(
            "external", "Open in system PDF viewer", self._emit_open_external
        )
        for w in (self._prev_match, self._next_match, self._external):
            row.addWidget(w)

        self._scroll = QScrollArea(self)
        self._scroll.setObjectName("pageView")
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._canvas = PageCanvas()
        self._scroll.setWidget(self._canvas)
        self._scroll.viewport().installEventFilter(_WheelZoomFilter(self))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addWidget(self._scroll, 1)
        self._update_controls()

    def _on_page_entered(self) -> None:
        text = self._page_spin.text()
        if text.isdigit():
            self.show_page(int(text) - 1)
        self._page_spin.setText(str(self._page + 1) if self._doc else "")

    def _emit_open_external(self) -> None:
        if self._path:
            self.open_external.emit(self._path, self._page + 1)

    # -- public API ----------------------------------------------------------------------

    @property
    def path(self) -> str | None:
        return self._path

    @property
    def page_index(self) -> int:
        return self._page

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    @property
    def fit_mode(self) -> str:
        return self._fit

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_highlight_provider(self, provider: HighlightProvider) -> None:
        self._provider = provider

    def set_view_mode(self, fit: str, zoom: float) -> None:
        self._fit = fit if fit in (FIT_WIDTH, FIT_PAGE, FIT_CUSTOM) else FIT_WIDTH
        self._zoom = max(ZOOM_STEPS[0], min(zoom, ZOOM_STEPS[-1]))
        self._update_controls()
        self._render()

    def open(self, path: str, page_index: int = 0, selected: Match | None = None) -> bool:
        """Show `path` at `page_index`. The document stays open while the same file is
        shown (NFR-PERF-05); opening another file closes it first (FR-VIEW-09)."""
        if path != self._path or self._doc is None:
            self.close_document(emit=False)
            try:
                self._doc = open_document(path)
            except PdfOpenError as exc:
                self._path = None
                self._show_message(f"Cannot open {os.path.basename(path)}\n({exc.reason})")
                self.open_failed.emit(f"Cannot open {path}: {exc.reason}")
                self.document_closed.emit()
                return False
            self._path = path
        self._selected = selected
        self._scroll_to_selected = selected is not None
        self.show_page(page_index, force=True)
        return True

    def close_document(self, emit: bool = True) -> None:
        if self._doc is not None:
            self._doc.close()
        self._doc = None
        self._path = None
        self._page = 0
        self._selected = None
        self._rect_cache.clear()
        self._show_empty()
        if emit:
            self.document_closed.emit()

    def show_page(self, index: int, force: bool = False) -> None:
        if self._doc is None:
            return
        index = max(0, min(index, self._doc.page_count - 1))
        if index == self._page and not force:
            return
        if index != self._page:
            self._doc.release_page(self._page)
        self._page = index
        self._update_controls()
        self._render()
        if self._path is not None:
            self.page_changed.emit(self._path, self._page, self._doc.page_count)

    def next_page(self) -> None:
        self.show_page(self._page + 1)

    def previous_page(self) -> None:
        self.show_page(self._page - 1)

    def refresh_highlights(self, clear_selection: bool = False) -> None:
        """Re-query the highlight provider, e.g. after a new search (FR-HL-04)."""
        if clear_selection:
            self._selected = None
        if self._doc is not None:
            self._canvas.set_marks(self._marks(self._current_scale()))

    def set_fit(self, fit: str) -> None:
        self._fit = fit
        self._update_controls()
        self._render()
        self.view_mode_changed.emit(self._fit, self._zoom)

    def zoom_in(self) -> None:
        self._step_zoom(+1)

    def zoom_out(self) -> None:
        self._step_zoom(-1)

    def schedule_relayout(self) -> None:
        if self._doc is not None and self._fit != FIT_CUSTOM:
            self._relayout_timer.start()
        elif self._doc is None:
            self._show_empty()

    # -- internals -----------------------------------------------------------------------

    def _step_zoom(self, direction: int) -> None:
        if self._doc is None:
            return
        current = self._current_scale() / POINTS_TO_PX
        if direction > 0:
            candidates = [z for z in ZOOM_STEPS if z > current * 1.01]
            new = candidates[0] if candidates else ZOOM_STEPS[-1]
        else:
            candidates = [z for z in ZOOM_STEPS if z < current * 0.99]
            new = candidates[-1] if candidates else ZOOM_STEPS[0]
        self._zoom = new
        self._fit = FIT_CUSTOM
        self._update_controls()
        self._render()
        self.view_mode_changed.emit(self._fit, self._zoom)

    def _available_size(self) -> tuple[float, float]:
        viewport = self._scroll.viewport()
        scrollbar = self._scroll.verticalScrollBar().sizeHint().width()
        width = max(50.0, self._scroll.width() - scrollbar - 2 * MARGIN)
        height = max(50.0, viewport.height() - 2 * MARGIN)
        return width, height

    def _current_scale(self) -> float:
        """Logical pixels per PDF point."""
        if self._doc is None:
            return POINTS_TO_PX
        page_w, page_h = self._doc.page_size(self._page)
        avail_w, avail_h = self._available_size()
        if self._fit == FIT_WIDTH:
            return avail_w / page_w
        if self._fit == FIT_PAGE:
            return min(avail_w / page_w, avail_h / page_h)
        return self._zoom * POINTS_TO_PX

    def _render(self) -> None:
        if self._doc is None or self._path is None:
            return
        scale = self._current_scale()
        dpr = self.devicePixelRatioF()
        try:
            rendered = self._doc.render(self._page, scale * dpr)
        except Exception as exc:  # a damaged page must not break the viewer
            self._show_message(f"Cannot render page {self._page + 1}: {exc}")
            return
        image = QImage(
            rendered.data,
            rendered.width,
            rendered.height,
            rendered.stride,
            QImage.Format.Format_ARGB32,
        ).copy()
        image.setDevicePixelRatio(dpr)
        page_w, page_h = self._doc.page_size(self._page)
        logical = QSize(round(page_w * scale), round(page_h * scale))
        self._canvas.set_page(image, logical, self._marks(scale))
        self._zoom_label.setText(f"{round(scale / POINTS_TO_PX * 100)} %")
        if self._scroll_to_selected:
            self._scroll_to_selected = False
            QTimer.singleShot(0, lambda: self._ensure_selected_visible(scale))

    def _rects(self, start: int, end: int) -> list[Rect]:
        assert self._doc is not None and self._path is not None
        key = (self._path, self._page, start, end)
        rects = self._rect_cache.get(key)
        if rects is None:
            try:
                rects = self._doc.char_rects(self._page, start, end)
            except Exception:
                rects = []
            self._rect_cache[key] = rects
        return rects

    def _marks(self, scale: float) -> list[_Mark]:
        """Marks for the matches of the current search on this page (FR-HL-01, FR-HL-06)."""
        if self._doc is None or self._path is None:
            return []
        marks: list[_Mark] = []
        selected_id = self._selected.match_id if self._selected is not None else None

        def to_view(r: Rect) -> QRectF:
            return QRectF(r.x0 * scale, r.y0 * scale, (r.x1 - r.x0) * scale, (r.y1 - r.y0) * scale)

        for match in self._provider(self._path, self._page):
            pm = match.page
            is_selected = match.match_id == selected_id
            if is_selected:
                for r in self._rects(pm.context_char_start, pm.context_char_end):
                    marks.append(_Mark(KIND_CONTEXT, to_view(r)))
            kind = KIND_SELECTED if is_selected else KIND_MATCH
            for r in self._rects(pm.char_start, pm.char_end):
                marks.append(_Mark(kind, to_view(r)))
        return marks

    def _ensure_selected_visible(self, scale: float) -> None:
        if self._selected is None or self._selected.page_index != self._page:
            return
        rects = self._rects(self._selected.page.char_start, self._selected.page.char_end)
        if not rects:
            return
        r = rects[0]
        x = int(MARGIN + (r.x0 + r.x1) / 2 * scale)
        y = int(MARGIN + (r.y0 + r.y1) / 2 * scale)
        viewport = self._scroll.viewport()
        self._scroll.ensureVisible(x, y, viewport.width() // 3, viewport.height() // 3)

    def _show_empty(self) -> None:
        self._show_message("Select a search result or a PDF file to view it here.")

    def _show_message(self, text: str) -> None:
        viewport = self._scroll.viewport().size() if hasattr(self, "_scroll") else QSize(400, 400)
        self._canvas.set_message(text, viewport)
        self._update_controls()

    def _update_controls(self) -> None:
        has_doc = self._doc is not None
        count = self._doc.page_count if self._doc else 0
        self._page_validator.setTop(max(1, count))
        self._page_spin.setText(str(self._page + 1) if has_doc else "")
        self._page_count.setText(f"/ {count}")
        for w in (
            self._page_spin,
            self._zoom_in,
            self._zoom_out,
            self._fit_width,
            self._fit_page,
            self._external,
        ):
            w.setEnabled(has_doc)
        self._prev_page.setEnabled(has_doc and self._page > 0)
        self._next_page.setEnabled(has_doc and self._page < count - 1)
        self._fit_width.setChecked(self._fit == FIT_WIDTH)
        self._fit_page.setChecked(self._fit == FIT_PAGE)
        self._title.setText(os.path.basename(self._path) if self._path else "")
        self._title.setToolTip(self._path or "")
        if not has_doc:
            self._zoom_label.setText("")
