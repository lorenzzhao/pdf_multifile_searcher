"""Text cache: hits, invalidation, corruption, permissions (FR-CACHE, NFR-SEC-04)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from pdf_multifile_searcher.cache import FileKey, TextCache
from pdf_multifile_searcher.core import textsource
from pdf_multifile_searcher.core.models import SearchQuery
from pdf_multifile_searcher.core.runner import FileFound, SearchRunner
from pdf_multifile_searcher.pdf_backend import BACKEND_ID


@pytest.fixture
def counting_extract(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = textsource.extract_text

    def wrapper(path: str) -> list[str]:
        calls.append(path)
        return real(path)

    monkeypatch.setattr(textsource, "extract_text", wrapper)
    return calls


def search_count(scope: Path, cache: Path, pattern: str = "needle") -> int:
    runner = SearchRunner([str(scope)], SearchQuery(pattern), cache_path=cache, in_process=True)
    return sum(len(e.result.matches) for e in runner.run() if isinstance(e, FileFound))


def test_unchanged_file_is_not_extracted_again(tmp_path, pdf_factory, counting_extract) -> None:
    pdf_factory("docs/a.pdf", ["needle one"])
    cache = tmp_path / "cache.sqlite3"
    assert search_count(tmp_path / "docs", cache) == 1
    assert search_count(tmp_path / "docs", cache) == 1
    assert len(counting_extract) == 1


def test_modified_file_is_extracted_again(tmp_path, pdf_factory, counting_extract) -> None:
    path = pdf_factory("docs/a.pdf", ["needle one"])
    cache = tmp_path / "cache.sqlite3"
    search_count(tmp_path / "docs", cache)
    pdf_factory("docs/a.pdf", ["needle one", "needle two"], ["needle three"])
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert search_count(tmp_path / "docs", cache) == 3
    assert len(counting_extract) == 2


def test_corrupt_cache_never_stops_a_search(tmp_path, pdf_factory) -> None:
    pdf_factory("docs/a.pdf", ["needle"])
    cache = tmp_path / "cache.sqlite3"
    cache.write_bytes(b"garbage, not a database" * 100)
    assert search_count(tmp_path / "docs", cache) == 1
    # The writer rebuilt the cache, so the next search can use it.
    assert search_count(tmp_path / "docs", cache) == 1
    reader = TextCache(cache, BACKEND_ID, readonly=True)
    assert reader.lookup(FileKey.for_file(str(tmp_path / "docs" / "a.pdf"))) is not None
    reader.close()


def test_cache_file_is_private(tmp_path, pdf_factory) -> None:
    pdf_factory("docs/a.pdf", ["needle"])
    cache = tmp_path / "private" / "cache.sqlite3"
    search_count(tmp_path / "docs", cache)
    assert stat.S_IMODE(cache.stat().st_mode) == 0o600


def test_backend_change_invalidates(tmp_path, pdf_factory) -> None:
    path = pdf_factory("a.pdf", ["x"])
    key = FileKey.for_file(str(path))
    writer = TextCache(tmp_path / "c.sqlite3", "engine-1")
    writer.store(key, ["x"], None)
    assert writer.lookup(key) is not None
    writer.close()
    other = TextCache(tmp_path / "c.sqlite3", "engine-2")
    assert other.lookup(key) is None
    other.close()


def test_prune_and_clear(tmp_path, pdf_factory) -> None:
    keep = pdf_factory("docs/keep.pdf", ["x"])
    gone = pdf_factory("docs/gone.pdf", ["x"])
    cache = TextCache(tmp_path / "c.sqlite3", BACKEND_ID)
    cache.store(FileKey.for_file(str(keep)), ["x"], None)
    cache.store(FileKey.for_file(str(gone)), ["x"], None)
    gone.unlink()
    assert cache.prune([str(tmp_path / "docs")]) == 1
    assert cache.size_bytes() > 0
    cache.clear()
    assert not (tmp_path / "c.sqlite3").exists()
