"""Search runner: sample data, IDs, skipped files, cancel (FR-SRCH, FR-MATCH-02, FR-ERR)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdf_multifile_searcher.core import textsource
from pdf_multifile_searcher.core.models import SearchOptions, SearchQuery, SearchSummary
from pdf_multifile_searcher.core.runner import FileFound, Finished, SearchRunner, Skipped
from pdf_multifile_searcher.pdf_backend import (
    REASON_DAMAGED,
    REASON_ENCRYPTED,
    REASON_NO_TEXT,
    PdfOpenError,
)


def run(runner: SearchRunner) -> tuple[list, list, SearchSummary]:
    matches, skipped, summary = [], [], None
    for event in runner.run():
        if isinstance(event, FileFound):
            matches.extend(event.result.matches)
        elif isinstance(event, Skipped):
            skipped.append(event.skipped)
        elif isinstance(event, Finished):
            summary = event.summary
    assert summary is not None
    return matches, skipped, summary


def search(scopes, pattern, **kwargs):
    options = SearchOptions(
        case_sensitive=kwargs.pop("case_sensitive", False),
        whole_word=kwargs.pop("whole_word", False),
        regex=kwargs.pop("regex", False),
    )
    kwargs.setdefault("in_process", True)
    runner = SearchRunner([str(s) for s in scopes], SearchQuery(pattern, options), **kwargs)
    return run(runner)


# Expected values for the committed sample PDFs in tests/data.
SAMPLE_EXPECTATIONS = [
    ("Zephyria", {}, 4, {"test_file_1.pdf"}),
    ("the", {}, 124, {"test_file_1.pdf", "test_file_4.pdf", "test_file_5.pdf"}),
    ("the", {"whole_word": True}, 112, None),
    ("The", {"case_sensitive": True}, 17, None),
    ("lorem ipsum", {}, 2, {"test_file_2.pdf", "test_file_3.pdf"}),
]


@pytest.mark.parametrize(("pattern", "options", "count", "files"), SAMPLE_EXPECTATIONS)
def test_sample_data(data_dir: Path, pattern, options, count, files) -> None:
    matches, skipped, summary = search([data_dir], pattern, **options)
    assert len(matches) == count == summary.matches
    assert skipped == []
    assert summary.files_searched == summary.files_total == 5
    if files is not None:
        assert {os.path.basename(m.path) for m in matches} == files


def test_zephyria_pages_and_context(data_dir: Path) -> None:
    matches, _, _ = search([data_dir], "Zephyria")
    assert {m.page_number for m in matches} == {1}
    assert all("zephyria" in m.context.lower() for m in matches)


def test_ids_are_unique_and_deterministic_across_scopes(data_dir: Path) -> None:
    scopes = [data_dir / "test_folder_b", data_dir / "test_folder_a"]
    first, _, _ = search(scopes, "the")
    pooled, _, _ = search(scopes, "the", in_process=False, workers=3)
    ids = [m.match_id for m in first]
    assert ids == list(range(len(first)))
    key = [(m.match_id, m.path, m.page.char_start) for m in first]
    assert key == [(m.match_id, m.path, m.page.char_start) for m in pooled]
    # Numbered by file path, then page, then position.
    order = [(m.path, m.page_index, m.page.char_start) for m in first]
    assert order == sorted(order)


def test_overlapping_scopes_search_each_file_once(data_dir: Path) -> None:
    matches, _, summary = search([data_dir, data_dir / "test_folder_a", data_dir], "Zephyria")
    assert len(matches) == 4
    assert summary.files_total == 5


def test_skipped_files_have_reasons(tmp_path: Path, pdf_factory, monkeypatch) -> None:
    pdf_factory("good.pdf", ["needle here"])
    pdf_factory("empty.pdf", [])
    (tmp_path / "broken.pdf").write_bytes(b"not a pdf at all")
    locked = pdf_factory("locked.pdf", ["needle"])
    real_extract = textsource.extract_text

    def fake_extract(path: str) -> list[str]:
        if path == str(locked):
            raise PdfOpenError(path, REASON_ENCRYPTED)
        return real_extract(path)

    monkeypatch.setattr(textsource, "extract_text", fake_extract)
    matches, skipped, summary = search([tmp_path, tmp_path / "missing"], "needle")
    reasons = {os.path.basename(s.path): s.reason for s in skipped}
    assert reasons == {
        "missing": "folder not available",
        "broken.pdf": REASON_DAMAGED,
        "empty.pdf": REASON_NO_TEXT,
        "locked.pdf": REASON_ENCRYPTED,
    }
    assert len(matches) == 1
    assert summary.skipped and summary.files_searched == 4


def test_cancel_before_start(data_dir: Path) -> None:
    runner = SearchRunner([str(data_dir)], SearchQuery("the"), in_process=True)
    runner.cancel()
    matches, _, summary = run(runner)
    assert matches == [] and summary.cancelled


def test_cancel_during_pool_search(data_dir: Path) -> None:
    runner = SearchRunner([str(data_dir)], SearchQuery("the"), workers=2)
    events = runner.run()
    for event in events:
        runner.cancel()
        if isinstance(event, Finished):
            assert event.summary.cancelled
            break
