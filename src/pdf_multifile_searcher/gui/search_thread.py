# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Runs a SearchRunner on a background thread and forwards its events (FR-SRCH-06)."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from pdf_multifile_searcher.core.runner import (
    FileFound,
    Finished,
    Progress,
    SearchRunner,
    Skipped,
    Started,
)

log = logging.getLogger(__name__)


class SearchThread(QThread):
    started_files = Signal(int)
    progress = Signal(int, int, int)
    file_found = Signal(object)  # FileMatches
    skipped = Signal(object)  # SkippedFile
    finished_search = Signal(object)  # SearchSummary
    failed = Signal(str)

    def __init__(self, runner: SearchRunner) -> None:
        super().__init__()
        self.runner = runner

    def cancel(self) -> None:
        self.runner.cancel()

    def run(self) -> None:
        try:
            for event in self.runner.run():
                if isinstance(event, FileFound):
                    self.file_found.emit(event.result)
                elif isinstance(event, Progress):
                    self.progress.emit(event.files_done, event.files_total, event.matches)
                elif isinstance(event, Skipped):
                    self.skipped.emit(event.skipped)
                elif isinstance(event, Started):
                    self.started_files.emit(event.files_total)
                elif isinstance(event, Finished):
                    self.finished_search.emit(event.summary)
        except Exception as exc:
            log.exception("Search failed")
            self.failed.emit(str(exc))
