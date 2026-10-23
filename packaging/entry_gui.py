# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Entry script of the standalone window program (PyInstaller)."""

import multiprocessing
import sys

from pdf_multifile_searcher.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # worker processes re-run this executable
    sys.exit(main())
