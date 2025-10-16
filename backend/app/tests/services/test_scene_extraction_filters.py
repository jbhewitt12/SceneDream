from bs4 import BeautifulSoup

from app.services.scene_extraction.scene_extraction import SceneExtractor


def _soup(body_fragment: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body>{body_fragment}</body></html>", "html.parser")


def test_skip_table_of_contents_block() -> None:
    extractor = SceneExtractor()
    soup = _soup("<div class='contents'><p>Contents</p></div>")
    should_skip = extractor._should_skip_spine_item(
        source_name="Text/book_con01.html",
        title="Contents",
        soup=soup,
        paragraphs=["Contents", "Chapter One"],
    )
    assert should_skip is True


def test_skip_front_matter_by_source_name() -> None:
    extractor = SceneExtractor()
    soup = _soup("<div class='halftitlepage'><p>Title</p></div>")
    should_skip = extractor._should_skip_spine_item(
        source_name="Text/book_htp01.html",
        title="THE NAME OF THE WIND",
        soup=soup,
        paragraphs=["THE NAME OF THE WIND"],
    )
    assert should_skip is True


def test_include_standard_chapter_document() -> None:
    extractor = SceneExtractor()
    soup = _soup("<div class='chapter'><p>Long narrative paragraph</p></div>")
    should_skip = extractor._should_skip_spine_item(
        source_name="Text/book_ch01.html",
        title="CHAPTER ONE",
        soup=soup,
        paragraphs=["A" * 120],
    )
    assert should_skip is False


def test_include_prologue_with_frontmatter_class() -> None:
    extractor = SceneExtractor()
    soup = _soup(
        "<div class='frontMatterPage'><div class='chapterBody'><p>Story</p></div></div>"
    )
    should_skip = extractor._should_skip_spine_item(
        source_name="Text/book_pro01.html",
        title="PROLOGUE A Beginning",
        soup=soup,
        paragraphs=["A" * 200],
    )
    assert should_skip is False
