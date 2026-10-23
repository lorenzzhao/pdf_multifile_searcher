# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025–2026 Lorenz Zhao
"""Data model shared by the search core, the CLI and the GUI."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_CONTEXT_WORDS = 10


@dataclass(frozen=True)
class SearchOptions:
    """How the pattern is interpreted (FR-SRCH-04, FR-SRCH-13)."""

    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False


@dataclass(frozen=True)
class SearchQuery:
    pattern: str
    options: SearchOptions = SearchOptions()
    context_words: int = DEFAULT_CONTEXT_WORDS


@dataclass(frozen=True)
class PageMatch:
    """One match on one page, as found by the matcher.

    Offsets are character indices into the page text returned by the PDF backend, so the
    viewer can turn them into rectangles on the page (FR-MATCH-01).
    """

    page_index: int
    char_start: int
    char_end: int
    context: str
    # Position of the matched text inside `context`, for emphasis (FR-MATCH-05).
    context_match_start: int
    context_match_end: int
    # Character range of the page text covered by the context (the context area).
    context_char_start: int
    context_char_end: int


@dataclass(frozen=True)
class Match:
    """A match with its file and its run-wide, deterministic ID (FR-MATCH-02)."""

    match_id: int
    path: str
    page: PageMatch

    @property
    def page_index(self) -> int:
        return self.page.page_index

    @property
    def page_number(self) -> int:
        """1-based page number, as shown to users (FR-RES-03)."""
        return self.page.page_index + 1

    @property
    def context(self) -> str:
        return self.page.context


@dataclass(frozen=True)
class FileMatches:
    """All matches of one file, in page and position order."""

    path: str
    matches: tuple[Match, ...]


@dataclass(frozen=True)
class SkippedFile:
    """A file or scope that could not be searched, with a user-facing reason (FR-ERR-02)."""

    path: str
    reason: str


@dataclass
class SearchSummary:
    """Totals shown when a search finishes or is cancelled (FR-SRCH-12)."""

    matches: int = 0
    files_with_matches: int = 0
    files_searched: int = 0
    files_total: int = 0
    skipped: list[SkippedFile] = field(default_factory=list)
    cancelled: bool = False
    seconds: float = 0.0
