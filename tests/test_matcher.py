"""Matcher tests on plain strings, without PDFs (NFR-TEST-05)."""

from __future__ import annotations

import pytest

from pdf_multifile_searcher.core.matcher import (
    PatternError,
    compile_query,
    find_in_page,
    normalize,
)
from pdf_multifile_searcher.core.models import SearchOptions, SearchQuery


def find(text: str, pattern: str, context_words: int = 10, **options: bool) -> list:
    query = compile_query(SearchQuery(pattern, SearchOptions(**options), context_words))
    return find_in_page(text, query, 0)


def matched_text(text: str, match) -> str:
    return text[match.char_start : match.char_end]


def test_default_is_literal_and_case_insensitive() -> None:
    text = "Price: 3.50 EUR. price list. PRICE"
    matches = find(text, "price")
    assert [matched_text(text, m) for m in matches] == ["Price", "price", "PRICE"]
    assert find("a.b axb", "a.b")[0].char_start == 0
    assert len(find("a.b axb", "a.b")) == 1  # "." is literal


def test_case_sensitive() -> None:
    assert len(find("Word word WORD", "word", case_sensitive=True)) == 1


def test_whole_word() -> None:
    text = "cat concatenate cat's bobcat"
    matches = find(text, "cat", whole_word=True)
    assert [m.char_start for m in matches] == [0, 16]


def test_regex() -> None:
    text = "order 12, order 345, order x"
    matches = find(text, r"order \d+", regex=True)
    assert [matched_text(text, m) for m in matches] == ["order 12", "order 345"]


def test_regex_whole_word_and_empty_matches_ignored() -> None:
    assert len(find("ab abc", "ab", regex=True, whole_word=True)) == 1
    assert find("abc", "x*", regex=True) == []


@pytest.mark.parametrize("pattern", ["", "   "])
def test_empty_pattern_rejected(pattern: str) -> None:
    with pytest.raises(PatternError):
        compile_query(SearchQuery(pattern))


def test_invalid_regex_rejected() -> None:
    with pytest.raises(PatternError, match="Invalid regular expression"):
        compile_query(SearchQuery("(", SearchOptions(regex=True)))


def test_line_breaks_and_whitespace_runs_match_a_space() -> None:
    text = "the quick\r\nbrown   fox"
    assert matched_text(text, find(text, "quick brown")[0]) == "quick\r\nbrown"
    assert len(find(text, "brown fox")) == 1


@pytest.mark.parametrize("marker", ["-\r\n", "￾", "\x02", "­"])
def test_hyphenated_word_found_unhyphenated(marker: str) -> None:
    text = f"an exam{marker}ple here"
    matches = find(text, "example")
    assert len(matches) == 1
    assert matched_text(text, matches[0]) == f"exam{marker}ple"
    assert "example" in matches[0].context


def test_hyphenated_compound_found_with_hyphen() -> None:
    text = "a well￾known fact"
    assert len(find(text, "well-known")) == 1
    assert len(find(text, "wellknown")) == 1


def test_whole_word_does_not_match_inside_hyphenated_word() -> None:
    assert find("an exam￾ple", "exam", whole_word=True) == []


def test_regex_runs_on_dehyphenated_text() -> None:
    text = "an exam￾ple"
    assert len(find(text, r"ex\w+e", regex=True)) == 1


def test_context_is_whole_words_with_ellipsis() -> None:
    text = " ".join(f"w{i}" for i in range(30))
    match = find(text, "w15", context_words=3)[0]
    assert match.context == "… w12 w13 w14 w15 w16 w17 w18 …"
    start, end = match.context_match_start, match.context_match_end
    assert match.context[start:end] == "w15"


def test_context_at_page_edges_has_no_ellipsis() -> None:
    match = find("alpha beta gamma", "alpha", context_words=5)[0]
    assert match.context == "alpha beta gamma"


def test_context_partial_word_match_keeps_whole_word() -> None:
    match = find("the magical relic", "magic", context_words=0)[0]
    assert match.context == "… magical …"
    assert match.context[match.context_match_start : match.context_match_end] == "magic"


def test_context_is_single_line() -> None:
    match = find("line one\r\nline two\r\nline three", "two", context_words=2)[0]
    assert "\n" not in match.context and "\r" not in match.context


def test_context_area_covers_context_words() -> None:
    text = "aaa bbb ccc ddd eee"
    match = find(text, "ccc", context_words=1)[0]
    assert text[match.context_char_start : match.context_char_end] == "bbb ccc ddd"


def test_normalize_maps_offsets_back() -> None:
    text = "ab  \r\n cd-\r\nef"
    norm = normalize(text)
    assert norm.text == "ab cd­ef"
    assert text[norm.to_original(norm.text.index("c"))] == "c"
    assert text[norm.to_original(norm.text.index("e"))] == "e"
