# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""PDF Multifile Searcher: search text in many PDF files at once."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "PDF Multifile Searcher"
APP_ID = "pdf-multifile-searcher"

try:
    __version__ = version("pdf-multifile-searcher")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "2.0.2"
