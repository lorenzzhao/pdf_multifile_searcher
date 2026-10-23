# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Shared fixtures. Test PDFs are generated with pypdfium2, so they are reproducible
(NFR-TEST-03); the committed sample PDFs in tests/data are used as-is."""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA_DIR = Path(__file__).parent / "data"


def make_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a PDF with one text line per list entry, using a standard font."""
    pdf = pdfium.PdfDocument.new()
    for lines in pages:
        page = pdf.new_page(595, 842)
        y = 800.0
        for line in lines:
            obj = pdfium_c.FPDFPageObj_NewTextObj(pdf.raw, b"Helvetica", 12.0)
            data = (line + "\0").encode("utf-16-le")
            text = (ctypes.c_ushort * (len(data) // 2)).from_buffer_copy(data)
            pdfium_c.FPDFText_SetText(obj, text)
            pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 50, y)
            pdfium_c.FPDFPage_InsertObject(page.raw, obj)
            y -= 16
        pdfium_c.FPDFPage_GenerateContent(page.raw)
        page.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(path))
    pdf.close()
    return path


@pytest.fixture
def pdf_factory(tmp_path: Path) -> Callable[..., Path]:
    def factory(name: str, *pages: list[str]) -> Path:
        return make_pdf(tmp_path / name, list(pages))

    return factory


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never touch the real config or cache directories."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
