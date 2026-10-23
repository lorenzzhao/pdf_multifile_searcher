"""Per-file search task, run in worker processes (FR-SRCH-05)."""

from __future__ import annotations

import functools
import logging
import signal
from dataclasses import dataclass
from pathlib import Path

from pdf_multifile_searcher.cache import FileKey
from pdf_multifile_searcher.core.matcher import CompiledQuery, compile_query, find_in_document
from pdf_multifile_searcher.core.models import PageMatch, SearchQuery
from pdf_multifile_searcher.core.textsource import CachedTextSource, DirectTextSource, PageTexts
from pdf_multifile_searcher.pdf_backend import REASON_NO_TEXT


@dataclass(frozen=True)
class FileTask:
    path: str
    query: SearchQuery
    cache_path: str | None


@dataclass(frozen=True)
class FileOutcome:
    path: str
    matches: list[PageMatch]
    error: str | None
    # Set when the text was freshly extracted, so the main process can cache it.
    cache_key: FileKey | None = None
    cache_pages: list[str] | None = None
    cache_error: str | None = None
    store_in_cache: bool = False


def init_worker(log_level: int = logging.WARNING) -> None:
    """Initializer for pool processes: Ctrl+C is handled by the parent only."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    logging.basicConfig(level=log_level)


@functools.lru_cache(maxsize=8)
def _compiled(query: SearchQuery) -> CompiledQuery:
    return compile_query(query)


def _get_texts(path: str, cache_path: str | None) -> PageTexts:
    if cache_path is None:
        return DirectTextSource().get(path)
    source = CachedTextSource(Path(cache_path))
    try:
        return source.get(path)
    finally:
        source.close()


def search_file(task: FileTask) -> FileOutcome:
    """Search one file. Never raises for problems with the file itself (FR-ERR-01)."""
    try:
        texts = _get_texts(task.path, task.cache_path)
    except Exception as exc:  # defensive: a library crash on one file must not stop the run
        logging.getLogger(__name__).exception("Unexpected error reading %s", task.path)
        return FileOutcome(task.path, [], f"cannot be read ({exc.__class__.__name__})")
    matches: list[PageMatch] = []
    error = texts.error
    if texts.pages is not None:
        if not any(page.strip() for page in texts.pages):
            error = REASON_NO_TEXT  # FR-ERR-07
        else:
            matches = find_in_document(texts.pages, _compiled(task.query))
    store = texts.fresh and texts.key is not None and task.cache_path is not None
    return FileOutcome(
        path=task.path,
        matches=matches,
        error=error,
        cache_key=texts.key if store else None,
        cache_pages=texts.pages if store else None,
        cache_error=texts.error if store else None,
        store_in_cache=store,
    )
