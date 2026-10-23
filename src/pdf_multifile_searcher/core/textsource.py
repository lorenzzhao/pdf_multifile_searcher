# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Where page text comes from (NFR-MAINT-06).

`TextSource` is the single interface the search uses to obtain page text. There are two
implementations: extracting directly from the PDF, and reading from the text cache with
direct extraction as the fallback. A future full-text index or OCR source can be added as
another implementation without touching the matcher, the result model or the GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pdf_multifile_searcher.cache import FileKey, TextCache
from pdf_multifile_searcher.pdf_backend import (
    BACKEND_ID,
    REASON_NOT_FOUND,
    REASON_PERMISSION,
    REASON_UNREADABLE,
    PdfOpenError,
    extract_text,
)


@dataclass(frozen=True)
class PageTexts:
    """Text of all pages of one file, or the reason it is unavailable."""

    key: FileKey | None
    pages: list[str] | None
    error: str | None
    # True when the text was freshly extracted and is worth storing in the cache.
    fresh: bool


class TextSource(Protocol):
    def get(self, path: str) -> PageTexts: ...


def _file_key(path: str) -> tuple[FileKey | None, str | None]:
    try:
        return FileKey.for_file(path), None
    except FileNotFoundError:
        return None, REASON_NOT_FOUND
    except PermissionError:
        return None, REASON_PERMISSION
    except OSError:
        return None, REASON_UNREADABLE


class DirectTextSource:
    """Always extract text from the PDF."""

    def get(self, path: str) -> PageTexts:
        key, error = _file_key(path)
        if key is None:
            return PageTexts(None, None, error, fresh=False)
        try:
            return PageTexts(key, extract_text(path), None, fresh=True)
        except PdfOpenError as exc:
            return PageTexts(key, None, exc.reason, fresh=True)


class CachedTextSource:
    """Read text from the cache (read-only); extract directly on a miss.

    Fresh results are returned with `fresh=True`; the caller decides whether to write them
    to the cache, so that only one process writes (FR-CACHE-07).
    """

    def __init__(self, cache_path: Path) -> None:
        self._cache = TextCache(cache_path, BACKEND_ID, readonly=True)
        self._direct = DirectTextSource()

    def get(self, path: str) -> PageTexts:
        key, error = _file_key(path)
        if key is None:
            return PageTexts(None, None, error, fresh=False)
        cached = self._cache.lookup(key)
        if cached is not None:
            return PageTexts(key, cached.pages, cached.error, fresh=False)
        return self._direct.get(path)

    def close(self) -> None:
        self._cache.close()
