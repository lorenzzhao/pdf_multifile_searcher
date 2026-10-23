# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Search scopes and file collection (FR-SCOPE-03, FR-SCOPE-06, FR-SCOPE-07, NFR-SEC-03)."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from pdf_multifile_searcher.core.models import SkippedFile

FOLDER_UNAVAILABLE = "folder not available"
FILE_UNAVAILABLE = "file not available"


def is_pdf_name(name: str) -> bool:
    return name.lower().endswith(".pdf")


def is_hidden_name(name: str) -> bool:
    return name.startswith(".")


def normalize_scope(path: str) -> str:
    """Absolute, normalised form of a user-supplied scope path (symlinks kept)."""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def same_scope(a: str, b: str) -> bool:
    """True if two scope paths refer to the same file or folder."""
    if normalize_scope(a) == normalize_scope(b):
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def iter_pdfs(folder: str, include_hidden: bool) -> Iterator[str]:
    """Yield every PDF below `folder`, following symlinks but never looping."""
    seen_dirs: set[tuple[int, int]] = set()
    stack = [folder]
    while stack:
        current = stack.pop()
        try:
            st = os.stat(current)
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen_dirs:
            continue
        seen_dirs.add(key)
        try:
            with os.scandir(current) as entries:
                children = sorted(entries, key=lambda e: e.name)
        except OSError:
            continue
        subdirs: list[str] = []
        for entry in children:
            if not include_hidden and is_hidden_name(entry.name):
                continue
            try:
                if entry.is_dir():
                    subdirs.append(entry.path)
                elif entry.is_file() and is_pdf_name(entry.name):
                    yield entry.path
            except OSError:
                continue
        stack.extend(reversed(subdirs))


@dataclass
class CollectedFiles:
    files: list[str] = field(default_factory=list)
    unavailable: list[SkippedFile] = field(default_factory=list)


def collect_files(scopes: Iterable[str], include_hidden: bool = False) -> CollectedFiles:
    """Collect the PDFs of all scopes into one sorted list without duplicates.

    A scope is either a folder (searched recursively) or a single PDF file. Duplicates are
    detected by resolved path, so repeated or nested scopes and symlinks never cause a file
    to be searched twice (FR-SCOPE-06). The result is sorted by path, which makes match IDs
    deterministic (FR-MATCH-02).
    """
    result = CollectedFiles()
    by_real: dict[str, str] = {}
    for scope in scopes:
        path = normalize_scope(scope)
        if os.path.isdir(path):
            candidates: Iterable[str] = iter_pdfs(path, include_hidden)
        elif os.path.isfile(path):
            candidates = [path]
        else:
            reason = FOLDER_UNAVAILABLE if not is_pdf_name(path) else FILE_UNAVAILABLE
            result.unavailable.append(SkippedFile(path, reason))
            continue
        for candidate in candidates:
            real = os.path.realpath(candidate)
            by_real.setdefault(real, candidate)
    result.files = sorted(by_real.values())
    return result
