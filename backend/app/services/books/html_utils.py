from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
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

FRONT_MATTER_SECTION_NAMES: set[str] = {
    "acknowledgments",
    "acknowledgements",
    "acknowledgment",
    "acknowledgement",
    "about the author",
    "also by",
    "books by",
    "copyright",
    "contents",
    "dedication",
    "table of contents",
    "title page",
}

FRONT_MATTER_PREFIXES: tuple[str, ...] = (
    "copyright",
    "all rights reserved",
    "no part of this publication",
    "this is a work of fiction",
    "isbn",
    "library of congress",
    "cover design",
    "printed in",
    "first edition",
    "visit our web site",
    "visit our website",
    "orbit is an imprint",
    "hachette book group",
    "acknowledgment",
    "acknowledgement",
    "acknowledgments",
    "acknowledgements",
    "table of contents",
    "contents",
    "about the author",
    "praise for",
    "also by",
    "books by",
)

FRONT_MATTER_PHRASES: tuple[str, ...] = (
    "table of contents",
    "all rights reserved",
    "no part of this publication",
    "this is a work of fiction",
    "copyright page",
    "cover design",
    "first edition",
    "library of congress",
    "for more information",
    "visit our web site",
    "visit our website",
    "hachette book group",
    "orbit is an imprint",
    "praise for",
    "also by",
    "books by",
    "acknowledgments",
    "acknowledgements",
)

FRONT_MATTER_CONTENT_TOKENS: set[str] = {
    "rights",
    "isbn",
    "acknowledgments",
    "acknowledgements",
    "dedication",
    "copyright",
    "publisher",
    "imprint",
    "advertisement",
    "advertisements",
    "appendix",
    "glossary",
    "index",
    "contents",
    "permission",
    "reproduction",
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

    # Files matching "index_split_NNN" pattern are Calibre-split content files,
    # not actual book indexes. Don't treat them as front matter.
    stem = Path(source_name).stem.lower()
    if re.match(r"^index_split_\d+$", stem):
        return False

    return bool(set(tokens) & name_tokens)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def is_front_matter_content(
    paragraphs: Sequence[str],
    *,
    heading: str | None = None,
) -> bool:
    """Heuristically determine if paragraph content is front/back matter."""
    if not paragraphs:
        return False

    heading_value = normalize_whitespace(heading).lower() if heading else None
    if heading_value:
        if heading_value in FRONT_MATTER_SECTION_NAMES:
            return True
        if set(_tokenize(heading_value)) & FRONT_MATTER_TOKENS:
            return True

    processed: list[tuple[str, str]] = [
        (normalized, normalized.lower())
        for normalized in (
            normalize_whitespace(paragraph) for paragraph in paragraphs if paragraph
        )
        if normalized
    ]
    if not processed:
        return False

    raw_window = [original for original, _ in processed[:20]]
    window = [lower for _, lower in processed[:20]]

    for candidate in window[:6]:
        for prefix in FRONT_MATTER_PREFIXES:
            if candidate.startswith(prefix):
                return True

    window_text = " ".join(window[:8])
    if any(phrase in window_text for phrase in FRONT_MATTER_PHRASES):
        return True

    tokens = _tokenize(" ".join(window[:8]))
    if not tokens:
        return False

    matches = [token for token in tokens if token in FRONT_MATTER_CONTENT_TOKENS]
    if len(matches) >= 3:
        return True

    unique_matches = set(matches)
    if len(unique_matches) >= 2 and len(matches) / max(len(tokens), 1) >= 0.2:
        return True

    catalog_titles = sum(
        1 for original in raw_window if _looks_like_catalog_title(original)
    )
    if catalog_titles >= 5 and catalog_titles / max(len(raw_window), 1) >= 0.5:
        return True

    if raw_window:
        first_line = raw_window[0]
        first_lower = window[0]
        if len(raw_window) <= 6 and len(first_line) <= 60:
            if first_lower.startswith(("for ", "to ", "with thanks", "with gratitude", "dedicated to")):
                return True
            if first_lower in {"for", "dedication"}:
                return True
        if first_lower.startswith("by ") and catalog_titles >= 3:
            return True

    return False


def _looks_like_catalog_title(value: str) -> bool:
    if not value:
        return False
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 60:
        return False
    if any(char in cleaned for char in ":;!?"):
        return False
    words = re.findall(r"[A-Za-z]+", cleaned)
    if not words or len(words) > 8:
        return False
    if any(word[:1].islower() for word in words):
        return False
    return True
