# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Preferences, problem list and About dialogs."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pdf_multifile_searcher import APP_NAME, __version__, legal, system
from pdf_multifile_searcher.config import Settings
from pdf_multifile_searcher.core.models import SkippedFile


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} bytes"


class PreferencesDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        cache_size: Callable[[], int],
        clear_cache: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(420)
        self._cache_size = cache_size
        self._clear_cache = clear_cache

        self.context_words = QSpinBox(self)
        self.context_words.setRange(0, 50)
        self.context_words.setValue(settings.context_words)
        self.context_words.setSuffix(" words")
        self.context_words.setToolTip("Words shown before and after each match in the result list")

        self.include_hidden = QCheckBox("Include hidden files and folders", self)
        self.include_hidden.setChecked(settings.include_hidden)
        self.include_hidden.setToolTip(
            "Names starting with a dot. Applies to the tree and the search."
        )

        self.use_cache = QCheckBox("Keep extracted text in a cache", self)
        self.use_cache.setChecked(settings.use_cache)
        self.use_cache.setToolTip("Repeat searches of unchanged files skip reading the PDFs.")

        self._cache_label = QLabel(self)
        self._cache_label.setObjectName("muted")
        clear = QPushButton("Clear text cache", self)
        clear.clicked.connect(self._on_clear)
        cache_row = QHBoxLayout()
        cache_row.addWidget(self._cache_label, 1)
        cache_row.addWidget(clear)
        self._update_cache_label()

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Context:", self.context_words)
        form.addRow("Files:", self.include_hidden)
        form.addRow("Text cache:", self.use_cache)
        form.addRow("", cache_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(8)
        layout.addWidget(buttons)

    def _update_cache_label(self) -> None:
        self._cache_label.setText(f"Cache size: {format_bytes(self._cache_size())}")

    def _on_clear(self) -> None:
        self._clear_cache()
        self._update_cache_label()

    def apply_to(self, settings: Settings) -> None:
        settings.context_words = self.context_words.value()
        settings.include_hidden = self.include_hidden.isChecked()
        settings.use_cache = self.use_cache.isChecked()


class ProblemsDialog(QDialog):
    """Files that were skipped, with the reason (FR-ERR-02)."""

    def __init__(self, skipped: list[SkippedFile], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Skipped files")
        self.resize(760, 380)
        intro = QLabel(
            f"{len(skipped)} file{'s were' if len(skipped) != 1 else ' was'} not searched. "
            "Files without a text layer are usually scanned documents.",
            self,
        )
        intro.setWordWrap(True)
        tree = QTreeWidget(self)
        tree.setHeaderLabels(["File", "Reason"])
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for item in skipped:
            row = QTreeWidgetItem([item.path, item.reason])
            row.setToolTip(0, item.path)
            tree.addTopLevelItem(row)
        tree.header().resizeSection(0, 560)
        tree.itemDoubleClicked.connect(lambda row, _col: system.show_in_file_manager(row.text(0)))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(tree, 1)
        layout.addWidget(buttons)


class TextViewDialog(QDialog):
    """Shows a plain-text document read-only, e.g. the license."""

    def __init__(self, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(720, 560)
        view = QPlainTextEdit(self)
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        view.setPlainText(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(view, 1)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    """Version, copyright, license, warranty disclaimer and source code link
    (the AGPL's "Appropriate Legal Notices")."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(480)
        text = QLabel(
            f"<h3>{APP_NAME} {__version__}</h3>"
            "<p>Search text in many PDF files at once and view the matches in place.</p>"
            f"<p>{legal.COPYRIGHT}</p>"
            f"<p>Licensed under the <a href='{legal.LICENSE_URL}'>{legal.LICENSE_NAME}</a>.<br>"
            f"Source code: <a href='{legal.SOURCE_URL}'>{legal.SOURCE_URL}</a></p>"
            f"<p>{legal.NO_WARRANTY}</p>"
            "<p>Uses Qt for Python (PySide6, LGPL-3.0), pypdfium2 and PDFium "
            "(Apache-2.0 / BSD-3-Clause) and platformdirs (MIT); see the third-party "
            "notices.</p>",
            self,
        )
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setOpenExternalLinks(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        self.license_button = self._text_button(buttons, "License…", legal.LICENSE_FILE, "License")
        self.notices_button = self._text_button(
            buttons, "Third-party notices…", legal.NOTICES_FILE, "Third-party notices"
        )
        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addSpacing(8)
        layout.addWidget(buttons)

    def _text_button(
        self, buttons: QDialogButtonBox, label: str, file_name: str, title: str
    ) -> QPushButton:
        button = buttons.addButton(label, QDialogButtonBox.ButtonRole.ActionRole)
        content = legal.read_bundled_text(file_name)
        if content is None:
            button.setEnabled(False)
            button.setToolTip(f"{file_name} is not installed with this copy of the program.")
        else:
            button.clicked.connect(lambda: TextViewDialog(title, content, self).exec())
        return button


def show_about(parent: QWidget) -> None:
    AboutDialog(parent).exec()
