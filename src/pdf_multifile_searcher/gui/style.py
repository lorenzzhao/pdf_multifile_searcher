# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Look and feel: Fusion style with a light and a dark theme that follow the system."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Theme:
    dark: bool
    window: str
    panel: str
    base: str
    alternate: str
    text: str
    muted: str
    border: str
    hover: str
    accent: str
    accent_text: str
    accent_soft: str
    error: str
    viewer_bg: str
    # Highlight colours on the page (FR-HL-02, NFR-UX-02). Fills use Qt's #AARRGGBB form.
    match_fill: str
    match_line: str
    selected_fill: str
    selected_line: str
    context_line: str


LIGHT = Theme(
    dark=False,
    window="#f3f4f6",
    panel="#f9fafb",
    base="#ffffff",
    alternate="#f8f9fb",
    text="#1f2937",
    muted="#6b7280",
    border="#d8dce3",
    hover="#e8ebf0",
    accent="#2563eb",
    accent_text="#ffffff",
    accent_soft="#dbe7fe",
    error="#dc2626",
    viewer_bg="#e3e6eb",
    match_fill="#66facc15",
    match_line="#ca8a04",
    selected_fill="#80f97316",
    selected_line="#c2410c",
    context_line="#2563eb",
)

DARK = Theme(
    dark=True,
    window="#1c1d21",
    panel="#202126",
    base="#25272c",
    alternate="#2a2c32",
    text="#e5e7eb",
    muted="#9ca3af",
    border="#3a3d45",
    hover="#30333a",
    accent="#3b82f6",
    accent_text="#ffffff",
    accent_soft="#1e3a6b",
    error="#f87171",
    viewer_bg="#141518",
    match_fill="#5cfacc15",
    match_line="#eab308",
    selected_fill="#80fb923c",
    selected_line="#fb923c",
    context_line="#60a5fa",
)


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def current_theme() -> Theme:
    return DARK if system_prefers_dark() else LIGHT


def _palette(t: Theme) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.window,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.base,
        QPalette.ColorRole.AlternateBase: t.alternate,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.base,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_text,
        QPalette.ColorRole.ToolTipBase: t.base,
        QPalette.ColorRole.ToolTipText: t.text,
        QPalette.ColorRole.PlaceholderText: t.muted,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.Mid: t.border,
        QPalette.ColorRole.Midlight: t.hover,
        QPalette.ColorRole.Light: t.base,
        QPalette.ColorRole.Dark: t.border,
    }
    for role, color in roles.items():
        p.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(t.muted))
    return p


def _stylesheet(t: Theme) -> str:
    return f"""
QMainWindow, QDialog {{ background: {t.window}; }}
QWidget#leftPanel, QWidget#viewerToolbar {{ background: {t.window}; }}
QSplitter::handle {{ background: {t.window}; }}
QSplitter::handle:hover {{ background: {t.border}; }}
QLabel#sectionTitle {{ color: {t.muted}; font-weight: 600; }}
QLabel#muted {{ color: {t.muted}; }}
QLabel#message {{ color: {t.error}; }}
QLabel#placeholder {{ color: {t.muted}; font-size: 11pt; }}
QLineEdit, QComboBox, QSpinBox {{
    background: {t.base}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 6px; padding: 4px 8px;
    selection-background-color: {t.accent}; selection-color: {t.accent_text};
}}
QSpinBox {{ padding: 2px 4px; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {t.accent}; }}
QLineEdit[invalid="true"], QComboBox[invalid="true"] {{ border-color: {t.error}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {t.base}; border: 1px solid {t.border}; outline: none;
    selection-background-color: {t.accent_soft}; selection-color: {t.text};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QToolButton {{
    color: {t.text}; background: transparent;
    border: 1px solid transparent; border-radius: 6px; padding: 3px;
}}
QToolButton:hover {{ background: {t.hover}; }}
QToolButton:pressed {{ background: {t.border}; }}
QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.accent}; color: {t.accent}; }}
QToolButton#option {{ font-weight: 600; min-width: 26px; }}
QPushButton {{
    background: {t.base}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 6px; padding: 5px 14px;
}}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton#primary {{
    background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {QColor(t.accent).lighter(112).name()}; }}
QPushButton#primary:disabled {{ background: {t.border}; border-color: {t.border}; }}
QTreeView {{
    background: {t.base}; alternate-background-color: {t.alternate}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 8px; outline: none;
}}
QTreeView::item {{ padding: 2px 0; }}
QTreeView::item:hover {{ background: {t.hover}; }}
QTreeView::item:selected {{ background: {t.accent_soft}; color: {t.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {t.panel}; color: {t.muted}; font-weight: 600;
    border: none; border-bottom: 1px solid {t.border}; padding: 4px 8px;
}}
QHeaderView::section:first {{ border-top-left-radius: 8px; }}
QHeaderView::section:last {{ border-top-right-radius: 8px; }}
QScrollArea#pageView {{ background: {t.viewer_bg}; border: none; }}
QScrollArea#pageView > QWidget > QWidget {{ background: {t.viewer_bg}; }}
QStatusBar {{ background: {t.panel}; color: {t.muted}; border-top: 1px solid {t.border}; }}
QStatusBar QLabel {{ color: {t.muted}; padding: 0 6px; }}
QProgressBar {{
    background: {t.border}; border: none; border-radius: 3px;
    max-height: 6px; min-width: 140px; text-align: center;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
QMenuBar {{ background: {t.window}; color: {t.text}; }}
QMenuBar::item:selected {{ background: {t.hover}; border-radius: 4px; }}
QMenu {{ background: {t.base}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t.accent_soft}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QToolTip {{ background: {t.base}; color: {t.text}; border: 1px solid {t.border}; padding: 4px; }}
"""


def apply_theme(app: QApplication, theme: Theme) -> None:
    app.setStyle("Fusion")
    app.setPalette(_palette(theme))
    app.setStyleSheet(_stylesheet(theme))
