# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""CSV export of search results (FR-RES-13, FR-CLI-08)."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from typing import TextIO

from pdf_multifile_searcher.core.models import Match

CSV_HEADER = ("file", "page", "context", "id")


def write_csv(matches: Iterable[Match], out: TextIO) -> int:
    """Write matches as CSV. Returns the number of rows written.

    Open `out` with ``newline=""``. For files meant for spreadsheet programs, use the
    ``utf-8-sig`` encoding so they detect UTF-8.
    """
    writer = csv.writer(out)
    writer.writerow(CSV_HEADER)
    count = 0
    for match in matches:
        writer.writerow((match.path, match.page_number, match.context, match.match_id))
        count += 1
    return count
