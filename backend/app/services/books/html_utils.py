from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from bs4 import BeautifulSoup

FRONT_MATTER_TOKENS: set[str] = {
    "ack",
    "acknowledge",
    "acknowledgement",
    "acknowledgements",
    "acknowledgment",
    "acknowledgments",
    "also",
    "author",
    "about",
    "ads",
    "advert",
    "advertisement",
    "afterword",
    "alsoby",
    "appendix",
    "bio",
    "colophon",
    "con",
    "contents",
    "copyright",
    "cop",
    "cover",
    "cov",
    "ded",
    "dedication",
    "excerpt",
    "fm",
    "foreword",
    "front",
    "glossary",
    "htp",
    "index",
    "intro",
    "introduction",
    "licence",
    "license",
    "map",
    "note",
    "notes",
    "pref",
    "preface",
    "praise",
    "promo",
    "sample",
    "sneak",
    "tit",
    "title",
    "toc",
}


def normalize_whitespace(text: str) -> str:
    """Collapse arbitrary whitespace into single spaces."""
    return " ".join(text.split())


def extract_paragraphs(soup: BeautifulSoup) -> list[str]:
    """Extract normalized paragraphs from a BeautifulSoup document."""
    paragraphs: list[str] = []

    for node in soup.find_all(["p", "div"]):
        if node.name != "p" and node.find("p"):
            continue
        text = normalize_whitespace(node.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)

    if paragraphs:
        return paragraphs

    # Fallback for documents that do not use block tags.
    raw_text = soup.get_text("\n")
    lines = [line.strip() for line in raw_text.splitlines()]
    buffer: list[str] = []

    for line in lines:
        if not line:
            if buffer:
                paragraphs.append(normalize_whitespace(" ".join(buffer)))
                buffer.clear()
            continue
        buffer.append(line)

    if buffer:
        paragraphs.append(normalize_whitespace(" ".join(buffer)))

    return [paragraph for paragraph in paragraphs if paragraph]


def extract_title(soup: BeautifulSoup) -> str | None:
    """Extract a likely chapter title from standard heading tags."""
    for selector in ("h1", "h2", "h3", "title"):
        node = soup.find(selector)
        if node:
            title = node.get_text(strip=True)
            if title:
                return normalize_whitespace(title)
    return None


def extract_name_tokens(source_name: str) -> set[str]:
    """Tokenize a source file name into lower-case alpha segments."""
    stem = Path(source_name).stem.lower()
    tokens = set(re.findall(r"[a-z]+", stem))
    generic_tokens = {"text", "section", "xhtml", "html"}
    return {token for token in tokens if token not in generic_tokens}


def looks_like_heading(text: str) -> bool:
    """Heuristically determine if the text resembles a heading."""
    if not text:
        return False
    if text.upper() == text and len(text) <= 120:
        return True

    lower = text.lower()
    if re.match(
        r"^(book|chapter|part|prologue|epilogue|interlude|act|scene)\b",
        lower,
    ):
        return True

    if not any(char in text for char in ".!?;:,"):
        words = text.split()
        if 1 <= len(words) <= 8 and all(word[:1].isalpha() for word in words):
            title_case_ratio = sum(1 for word in words if word[:1].isupper())
            if title_case_ratio == len(words):
                return True

    return False


def is_front_matter(
    source_name: str,
    tokens: Iterable[str] = FRONT_MATTER_TOKENS,
) -> bool:
    """Return True when the source name suggests front-matter content."""
    name_tokens = extract_name_tokens(source_name)
    if not name_tokens:
        return False
    return bool(set(tokens) & name_tokens)
