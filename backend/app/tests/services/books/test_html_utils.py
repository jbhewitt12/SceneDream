from __future__ import annotations

from bs4 import BeautifulSoup

from app.services.books.html_utils import (
    extract_name_tokens,
    extract_paragraphs,
    extract_title,
    is_front_matter,
    looks_like_heading,
    normalize_whitespace,
)


def test_normalize_whitespace_collapses_spaces() -> None:
    assert normalize_whitespace("  Hello   world\t") == "Hello world"


def test_extract_paragraphs_basic() -> None:
    html = "<p>First para.</p><p>Second para.</p>"
    soup = BeautifulSoup(html, "html.parser")
    result = extract_paragraphs(soup)
    assert result == ["First para.", "Second para."]


def test_extract_paragraphs_collapses_blank_lines() -> None:
    html = "<div>Line one<br/>Line two</div><div>Next</div>"
    soup = BeautifulSoup(html, "html.parser")
    result = extract_paragraphs(soup)
    assert result == ["Line one Line two", "Next"]


def test_extract_title_prefers_heading() -> None:
    html = "<html><body><h2>Chapter One</h2></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert extract_title(soup) == "Chapter One"


def test_extract_title_none_when_missing() -> None:
    soup = BeautifulSoup("<p>No heading here</p>", "html.parser")
    assert extract_title(soup) is None


def test_looks_like_heading_variants() -> None:
    assert looks_like_heading("CHAPTER FIVE")
    assert looks_like_heading("Chapter 5: Into the Fire")
    assert not looks_like_heading("This is a normal sentence.")


def test_is_front_matter_detects_common_tokens() -> None:
    assert is_front_matter("copyright.xhtml")
    assert is_front_matter("fm_01_dedication.html")
    assert not is_front_matter("chapter003.xhtml")


def test_extract_name_tokens_filters_generics() -> None:
    tokens = extract_name_tokens("Text_Section_HTML.xhtml")
    assert tokens == set()
