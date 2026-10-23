"""PDF backend adapter (NFR-MAINT-02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdf_multifile_searcher.core.matcher import compile_query, find_in_page
from pdf_multifile_searcher.core.models import SearchQuery
from pdf_multifile_searcher.pdf_backend import (
    REASON_DAMAGED,
    REASON_NOT_FOUND,
    PdfOpenError,
    extract_text,
    open_document,
)


def test_extract_text_per_page(pdf_factory) -> None:
    path = pdf_factory("two.pdf", ["first page"], ["second page"])
    pages = extract_text(str(path))
    assert [p.strip() for p in pages] == ["first page", "second page"]


def test_char_rects_cover_the_match(pdf_factory) -> None:
    path = pdf_factory("rects.pdf", ["left middle right"])
    with open_document(str(path)) as doc:
        text = doc.page_text(0)
        match = find_in_page(text, compile_query(SearchQuery("middle")), 0)[0]
        rects = doc.char_rects(0, match.char_start, match.char_end)
        width, height = doc.page_size(0)
    assert len(rects) == 1
    r = rects[0]
    # The line is drawn at x=50, baseline y=800 from the bottom of an 842 pt page.
    assert 50 < r.x0 < r.x1 < width
    assert 30 < r.y0 < r.y1 < 60
    assert (width, height) == pytest.approx((595, 842))


def test_render_returns_bgra_pixels(pdf_factory) -> None:
    path = pdf_factory("render.pdf", ["x"])
    with open_document(str(path)) as doc:
        rendered = doc.render(0, 0.5)
    assert rendered.width == pytest.approx(298, abs=1)
    assert len(rendered.data) == rendered.stride * rendered.height


def test_open_errors_are_typed(tmp_path: Path) -> None:
    with pytest.raises(PdfOpenError) as missing:
        open_document(str(tmp_path / "missing.pdf"))
    assert missing.value.reason == REASON_NOT_FOUND
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"this is not a pdf")
    with pytest.raises(PdfOpenError) as damaged:
        open_document(str(broken))
    assert damaged.value.reason == REASON_DAMAGED


def test_sample_pdfs_open(data_dir: Path) -> None:
    for path in sorted(data_dir.rglob("*.pdf")):
        assert any(page.strip() for page in extract_text(str(path)))
