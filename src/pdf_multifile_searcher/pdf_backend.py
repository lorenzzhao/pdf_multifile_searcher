# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""PDF backend adapter (NFR-MAINT-02, NFR-LIC-03).

All calls into the PDF library go through this module. The rest of the program only uses
`open_document`, `PdfDocumentHandle`, `PdfOpenError` and the plain data types defined here,
so the engine (currently pypdfium2) can be swapped without changes elsewhere.

PDFium is not thread-safe: a process must only use this module from one thread at a time.
The GUI uses it on the main thread, and searches run in separate worker processes.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

# Identifies the extraction engine; stored with cached text so an engine change
# invalidates the cache (FR-CACHE-02).
BACKEND_ID = f"pypdfium2 {pdfium.version.PYPDFIUM_INFO} / pdfium {pdfium.version.PDFIUM_INFO}"

# Reasons shown to the user when a file cannot be searched (FR-ERR-02).
REASON_ENCRYPTED = "encrypted"
REASON_DAMAGED = "damaged"
REASON_PERMISSION = "permission denied"
REASON_NOT_FOUND = "file not found"
REASON_UNREADABLE = "cannot be read"
REASON_NO_TEXT = "no text layer"


class PdfOpenError(Exception):
    """A document cannot be opened. `reason` is one of the REASON_* constants."""

    def __init__(self, path: str, reason: str, detail: str = "") -> None:
        super().__init__(f"{path}: {reason}" + (f" ({detail})" if detail else ""))
        self.path = path
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Rect:
    """A rectangle in device-independent page coordinates, origin top left."""

    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class RenderedPage:
    """A rendered page as tightly packed 32-bit BGRA pixels."""

    width: int
    height: int
    stride: int
    data: bytes


_ERROR_REASONS = {
    pdfium_c.FPDF_ERR_PASSWORD: REASON_ENCRYPTED,
    pdfium_c.FPDF_ERR_SECURITY: REASON_ENCRYPTED,
    pdfium_c.FPDF_ERR_FORMAT: REASON_DAMAGED,
    pdfium_c.FPDF_ERR_FILE: REASON_UNREADABLE,
}


def open_document(path: str) -> PdfDocumentHandle:
    """Open a PDF. Raises PdfOpenError with a typed reason on failure."""
    try:
        with open(path, "rb") as fh:
            fh.read(1)
    except FileNotFoundError as exc:
        raise PdfOpenError(path, REASON_NOT_FOUND) from exc
    except PermissionError as exc:
        raise PdfOpenError(path, REASON_PERMISSION) from exc
    except OSError as exc:
        raise PdfOpenError(path, REASON_UNREADABLE, str(exc)) from exc
    try:
        doc = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        code = getattr(exc, "err_code", None)
        reason = _ERROR_REASONS.get(code, REASON_DAMAGED) if code is not None else REASON_DAMAGED
        raise PdfOpenError(path, reason, str(exc)) from exc
    except OSError as exc:
        raise PdfOpenError(path, REASON_UNREADABLE, str(exc)) from exc
    return PdfDocumentHandle(path, doc)


class PdfDocumentHandle:
    """An open document. Close it with `close()` or use it as a context manager."""

    def __init__(self, path: str, doc: Any) -> None:
        self.path = path
        self._doc = doc
        self._text_pages: dict[int, Any] = {}
        self._pages: dict[int, Any] = {}

    def __enter__(self) -> PdfDocumentHandle:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        for tp in self._text_pages.values():
            tp.close()
        for page in self._pages.values():
            page.close()
        self._text_pages.clear()
        self._pages.clear()
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def _page(self, index: int) -> Any:
        page = self._pages.get(index)
        if page is None:
            page = self._doc[index]
            self._pages[index] = page
        return page

    def _text_page(self, index: int) -> Any:
        tp = self._text_pages.get(index)
        if tp is None:
            tp = self._page(index).get_textpage()
            self._text_pages[index] = tp
        return tp

    def release_page(self, index: int) -> None:
        """Free cached page objects; used when iterating a whole document."""
        tp = self._text_pages.pop(index, None)
        if tp is not None:
            tp.close()
        page = self._pages.pop(index, None)
        if page is not None:
            page.close()

    def page_size(self, index: int) -> tuple[float, float]:
        """Page width and height in points, after the page's own rotation."""
        width, height = self._page(index).get_size()
        return float(width), float(height)

    def page_text(self, index: int) -> str:
        """The page text. Offset i corresponds to character box i (see `char_rects`)."""
        tp = self._text_page(index)
        count = tp.count_chars()
        if count <= 0:
            return ""
        text: str = tp.get_text_range(0, count)
        if len(text) != count:
            # Characters outside the BMP make the UTF-16 range differ from char indices.
            raw = tp.raw
            text = "".join(
                chr(pdfium_c.FPDFText_GetUnicode(raw, i) or 0xFFFD) for i in range(count)
            )
        return text

    def char_rects(self, index: int, start: int, end: int) -> list[Rect]:
        """Rectangles covering characters [start, end), one per text line, in page points
        with the origin at the top left of the displayed (rotated) page."""
        if end <= start:
            return []
        tp = self._text_page(index)
        page = self._page(index)
        width, height = self.page_size(index)
        # Use a large virtual device so rounding in FPDF_PageToDevice stays below 0.01 pt.
        scale = 100.0
        dev_w, dev_h = round(width * scale), round(height * scale)
        rects: list[Rect] = []
        n = tp.count_rects(start, end - start)
        for i in range(n):
            left, bottom, right, top = tp.get_rect(i)
            x0, y0 = _page_to_device(page.raw, dev_w, dev_h, left, top)
            x1, y1 = _page_to_device(page.raw, dev_w, dev_h, right, bottom)
            rects.append(
                Rect(
                    min(x0, x1) / scale,
                    min(y0, y1) / scale,
                    max(x0, x1) / scale,
                    max(y0, y1) / scale,
                )
            )
        return rects

    def render(self, index: int, scale: float) -> RenderedPage:
        """Render a page at `scale` pixels per point."""
        page = self._page(index)
        bitmap = page.render(
            scale=scale,
            force_bitmap_format=pdfium_c.FPDFBitmap_BGRA,
            may_draw_forms=True,
        )
        try:
            data = bytes(bitmap.buffer)
            return RenderedPage(bitmap.width, bitmap.height, bitmap.stride, data)
        finally:
            bitmap.close()


def _page_to_device(raw_page: Any, dev_w: int, dev_h: int, x: float, y: float) -> tuple[int, int]:
    dx = ctypes.c_int()
    dy = ctypes.c_int()
    pdfium_c.FPDF_PageToDevice(raw_page, 0, 0, dev_w, dev_h, 0, x, y, dx, dy)
    return dx.value, dy.value


def extract_text(path: str) -> list[str]:
    """Extract the text of every page. Raises PdfOpenError if the file cannot be opened."""
    with open_document(path) as doc:
        pages: list[str] = []
        for index in range(doc.page_count):
            try:
                pages.append(doc.page_text(index))
            except Exception:  # one broken page must not abort the file (FR-ERR-03)
                pages.append("")
            finally:
                doc.release_page(index)
        return pages
