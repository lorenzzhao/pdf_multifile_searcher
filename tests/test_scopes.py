# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""File collection across scopes (FR-SCOPE-03, FR-SCOPE-06, FR-SCOPE-07, NFR-SEC-03)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pdf_multifile_searcher.core.scopes import (
    FOLDER_UNAVAILABLE,
    collect_files,
    same_scope,
)


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n")
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    touch(root / "a.pdf")
    touch(root / "B.PDF")
    touch(root / "notes.txt")
    touch(root / "sub" / "c.pdf")
    touch(root / "sub" / "deeper" / "deepest" / "d.pdf")
    touch(root / ".hidden" / "e.pdf")
    touch(root / ".f.pdf")
    return root


def names(paths: list[str]) -> list[str]:
    return sorted(os.path.basename(p) for p in paths)


def test_recursive_and_case_insensitive_extension(tree: Path) -> None:
    result = collect_files([str(tree)])
    assert names(result.files) == ["B.PDF", "a.pdf", "c.pdf", "d.pdf"]
    assert result.files == sorted(result.files)


def test_hidden_files_follow_the_setting(tree: Path) -> None:
    assert ".f.pdf" not in names(collect_files([str(tree)]).files)
    with_hidden = names(collect_files([str(tree)], include_hidden=True).files)
    assert ".f.pdf" in with_hidden and "e.pdf" in with_hidden


def test_nested_and_repeated_scopes_are_deduplicated(tree: Path) -> None:
    result = collect_files([str(tree), str(tree / "sub"), str(tree), str(tree / "a.pdf")])
    assert len(result.files) == 4


def test_single_file_scope_searches_only_that_file(tree: Path) -> None:
    assert names(collect_files([str(tree / "sub" / "c.pdf")]).files) == ["c.pdf"]


def test_missing_scope_is_reported(tmp_path: Path) -> None:
    result = collect_files([str(tmp_path / "gone")])
    assert result.files == []
    assert result.unavailable[0].reason == FOLDER_UNAVAILABLE


def test_symlink_loop_terminates_and_symlinked_file_counted_once(tree: Path) -> None:
    (tree / "sub" / "loop").symlink_to(tree, target_is_directory=True)
    (tree / "link.pdf").symlink_to(tree / "a.pdf")
    result = collect_files([str(tree)])
    assert len(result.files) == 4


def test_same_scope(tree: Path) -> None:
    assert same_scope(str(tree), str(tree / "sub" / ".."))
    assert not same_scope(str(tree), str(tree / "sub"))
