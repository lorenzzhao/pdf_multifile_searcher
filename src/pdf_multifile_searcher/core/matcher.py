"""The program's own matcher (FR-SRCH-04, FR-SRCH-13, FR-SRCH-17, FR-MATCH-04).

The matcher is a pure function from page text and a query to matches (NFR-MAINT-07). It
never touches files or the PDF library.

Page text is first normalised:

* every run of whitespace, including line breaks, becomes a single space;
* a hyphen at the end of a line (directly after a letter or digit) is joined with the next
  line and replaced by an invisible marker (U+00AD SOFT HYPHEN), so "exam-<newline>ple" can
  be found as "example" while "well-<newline>known" can still be found as "well-known";
* soft hyphens and PDFium's hyphenation markers also become the marker. PDFium reports a
  hyphen at a line end as U+FFFE (and joins the lines), or sometimes as U+0002.

Every normalised character keeps a link to its offset in the original page text, so
matches can be mapped back to character boxes on the page.
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from pdf_multifile_searcher.core.models import PageMatch, SearchQuery

SHY = "\u00ad"  # marker for a hyphenation point in normalised text
# Hyphen characters in patterns and at line ends: hyphen-minus, soft hyphen, hyphen, and
# PDFium's markers U+0002 and U+FFFE.
_HYPHENS = "-\u00ad\u2010\x02\ufffe"

_SPECIAL = re.compile(
    "(?P<hy>(?<=\\w)[-\u00ad\u2010\x02\ufffe][ \\t]*(?:\\r\\n|\\r|\\n|\u2028|\u2029)\\s*)"
    "|(?P<ws>[\\s\x00\x01\x03-\x1f]+)"
    "|(?P<shy>[\u00ad\x02\ufffe])"
)


class PatternError(ValueError):
    """The search pattern is empty or not a valid regular expression."""


@dataclass(frozen=True)
class NormalizedText:
    text: str
    # Contiguous segments: normalised offset `norm_starts[k]` corresponds to original offset
    # `orig_starts[k]`, and both advance together until the next segment starts.
    norm_starts: tuple[int, ...]
    orig_starts: tuple[int, ...]
    orig_length: int

    def to_original(self, norm_offset: int) -> int:
        if not self.norm_starts:
            return 0
        k = bisect.bisect_right(self.norm_starts, norm_offset) - 1
        k = max(k, 0)
        return min(self.orig_starts[k] + (norm_offset - self.norm_starts[k]), self.orig_length)


def normalize(text: str, keep_hyphen_marker: bool = True) -> NormalizedText:
    """Normalise page text as described in the module docstring."""
    parts: list[str] = []
    norm_starts: list[int] = []
    orig_starts: list[int] = []
    length = 0
    last_char = ""

    def emit(chunk: str, orig: int) -> None:
        nonlocal length, last_char
        if not chunk:
            return
        norm_starts.append(length)
        orig_starts.append(orig)
        parts.append(chunk)
        length += len(chunk)
        last_char = chunk[-1]

    pos = 0
    for m in _SPECIAL.finditer(text):
        emit(text[pos : m.start()], pos)
        if m.lastgroup == "ws":
            if length and last_char != " ":
                emit(" ", m.start())
        elif keep_hyphen_marker:
            emit(SHY, m.start())
        pos = m.end()
    emit(text[pos:], pos)
    return NormalizedText("".join(parts), tuple(norm_starts), tuple(orig_starts), len(text))


@dataclass(frozen=True)
class CompiledQuery:
    regex: re.Pattern[str]
    keep_hyphen_marker: bool
    context_words: int


def _literal_regex(pattern: str) -> str:
    """Regex for a literal pattern that tolerates line-end hyphenation markers."""
    words = pattern.split()
    pieces: list[str] = []
    for w_index, word in enumerate(words):
        if w_index:
            pieces.append(" ")
        for c_index, char in enumerate(word):
            if c_index:
                pieces.append(f"{SHY}?")
            if char in _HYPHENS:
                pieces.append(f"(?:-|\u2010|{SHY})")
            else:
                pieces.append(re.escape(char))
    return "".join(pieces)


def compile_query(query: SearchQuery) -> CompiledQuery:
    """Validate and compile a query. Raises PatternError for unusable patterns."""
    pattern = query.pattern
    if not pattern.strip():
        raise PatternError("Enter a search pattern.")
    flags = 0 if query.options.case_sensitive else re.IGNORECASE
    if query.options.regex:
        body = pattern
        keep_marker = False
        boundary_chars = r"\w"
    else:
        body = _literal_regex(pattern)
        keep_marker = True
        boundary_chars = rf"\w{SHY}"
    if query.options.whole_word:
        body = rf"(?<![{boundary_chars}])(?:{body})(?![{boundary_chars}])"
    try:
        regex = re.compile(body, flags)
    except re.error as exc:
        raise PatternError(f"Invalid regular expression: {exc}") from exc
    return CompiledQuery(regex, keep_marker, max(0, query.context_words))


def _context_bounds(text: str, start: int, end: int, words: int) -> tuple[int, int]:
    """Extend [start, end) to whole words plus `words` words on each side."""
    left = start
    while left > 0 and text[left - 1] != " ":
        left -= 1
    for _ in range(words):
        if left == 0:
            break
        while left > 0 and text[left - 1] == " ":
            left -= 1
        while left > 0 and text[left - 1] != " ":
            left -= 1
    right = end
    n = len(text)
    while right < n and text[right] != " ":
        right += 1
    for _ in range(words):
        if right >= n:
            break
        while right < n and text[right] == " ":
            right += 1
        while right < n and text[right] != " ":
            right += 1
    return left, right


def find_in_page(page_text: str, query: CompiledQuery, page_index: int) -> list[PageMatch]:
    """Return all matches of `query` in one page's text, in reading order."""
    if not page_text:
        return []
    norm = normalize(page_text, query.keep_hyphen_marker)
    text = norm.text
    results: list[PageMatch] = []
    for m in query.regex.finditer(text):
        ns, ne = m.span()
        if ne <= ns:
            continue  # ignore empty regex matches
        left, right = _context_bounds(text, ns, ne, query.context_words)
        before = text[left:ns].lstrip().replace(SHY, "")
        matched = text[ns:ne].replace(SHY, "")
        after = text[ne:right].rstrip().replace(SHY, "")
        lead = "… " if left > 0 else ""
        tail = " …" if right < len(text.rstrip()) else ""
        context = f"{lead}{before}{matched}{after}{tail}"
        match_start = len(lead) + len(before)
        results.append(
            PageMatch(
                page_index=page_index,
                char_start=norm.to_original(ns),
                char_end=norm.to_original(ne - 1) + 1,
                context=context,
                context_match_start=match_start,
                context_match_end=match_start + len(matched),
                context_char_start=norm.to_original(left),
                context_char_end=norm.to_original(max(left, right - 1)) + 1,
            )
        )
    return results


def find_in_document(pages: list[str], query: CompiledQuery) -> list[PageMatch]:
    matches: list[PageMatch] = []
    for index, text in enumerate(pages):
        matches.extend(find_in_page(text, query, index))
    return matches
