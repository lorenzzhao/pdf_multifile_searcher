# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""A small set of line icons drawn as SVG and tinted to the current palette.

Icons follow the palette at paint time, so they stay legible in light and dark mode and are
sharp at any device pixel ratio.
"""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QByteArray, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QIconEngine, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24×24 stroke paths. Drawn for this project.
_PATHS: dict[str, str] = {
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "folder-plus": (
        '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<path d="M12 10.5v5M9.5 13h5"/>'
    ),
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
    "file-plus": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5M12 11v6M9 14h6"/>'
    ),
    "file-pdf": (
        '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
        '<path d="M14 3v5h5M8.5 13h7M8.5 16.5h5"/>'
    ),
    "open": (
        '<path d="M4 20V6a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v2"/>'
        '<path d="M4 20l3.2-8.1A2 2 0 0 1 9 10.6h11.5l-3.4 8.6A1.3 1.3 0 0 1 16 20z"/>'
    ),
    "minus": '<path d="M5 12h14"/>',
    "trash": (
        '<path d="M4 7h16M10 11v6M14 11v6"/>'
        '<path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>'
    ),
    "refresh": '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v5h-5"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "chevron-left": '<path d="M15 6l-6 6 6 6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "zoom-in": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6M11 8v6"/>',
    "zoom-out": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6"/>',
    "fit-width": '<path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4"/>',
    "fit-page": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "external": (
        '<path d="M14 4h6v6M20 4l-9 9"/>'
        '<path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'
    ),
    "export": '<path d="M12 3v12M8 11l4 4 4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "settings": (
        '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/>'
        '<circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>'
    ),
    "warning": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "app": (
        '<path d="M13 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4"/><path d="M13 3v5h5V11"/>'
        '<circle cx="16.5" cy="16.5" r="3.5"/><path d="M21 21l-2-2"/>'
    ),
}

# Fixed colours for icons that carry meaning (folder, PDF, warning).
FOLDER_COLOR = QColor("#d39b1f")
PDF_COLOR = QColor("#d1443c")
WARNING_COLOR = QColor("#d97706")
ACCENT_ICON_COLOR = QColor("#2563eb")


def _svg(name: str, color: QColor, stroke_width: float) -> bytes:
    body = _PATHS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color.name()}" stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    ).encode()


class _TintedSvgEngine(QIconEngine):
    def __init__(self, name: str, color: QColor | None, stroke_width: float) -> None:
        super().__init__()
        self._name = name
        self._color = color
        self._stroke_width = stroke_width

    def _color_for(self, mode: QIcon.Mode) -> QColor:
        palette = QGuiApplication.palette()
        if mode == QIcon.Mode.Disabled:
            return palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text)
        if mode == QIcon.Mode.Selected and self._color is None:
            return palette.color(QPalette.ColorRole.HighlightedText)
        if self._color is not None:
            return self._color
        return palette.color(QPalette.ColorRole.Text)

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        renderer = QSvgRenderer(
            QByteArray(_svg(self._name, self._color_for(mode), self._stroke_width))
        )
        renderer.render(painter, QRectF(rect))

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        painter.end()
        return pixmap

    def clone(self) -> QIconEngine:
        return _TintedSvgEngine(self._name, self._color, self._stroke_width)


def app_icon() -> QIcon:
    """The application icon (also used for the packaged programs)."""
    try:
        data = (
            resources.files("pdf_multifile_searcher") / "resources" / "app-icon.svg"
        ).read_bytes()
    except OSError:
        return icon("app")
    renderer = QSvgRenderer(QByteArray(data))
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        result.addPixmap(pixmap)
    return result


def icon(name: str, color: QColor | None = None, stroke_width: float = 1.8) -> QIcon:
    """An icon by name. Without `color`, it follows the palette's text colour."""
    return QIcon(_TintedSvgEngine(name, color, stroke_width))
