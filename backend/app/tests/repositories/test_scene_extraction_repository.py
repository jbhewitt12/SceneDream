"""Tests for SceneExtractionRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

from sqlmodel import Session

from app.repositories import SceneExtractionRepository


def _scene_payload(**overrides: object) -> dict[str, object]:
    book_slug = str(overrides.get("book_slug", f"test-book-scene-repo-{uuid4()}"))
    chapter_number = int(overrides.get("chapter_number", 1))
    scene_number = int(overrides.get("scene_number", 1))
    data: dict[str, object] = {
        "book_slug": book_slug,
        "source_book_path": "documents/test.epub",
        "chapter_number": chapter_number,
        "chapter_title": "Repository Chapter",
        "chapter_source_name": "chapter1.xhtml",
        "scene_number": scene_number,
        "location_marker": f"{book_slug}-{chapter_number}-{scene_number}",
        "raw": "An observatory rotates toward a fractured moon.",
        "refined": "An observatory rotates toward a fractured moon above frozen seas.",
        "refinement_decision": "keep",
        "refinement_rationale": "Rich visual detail.",
        "chunk_index": 0,
        "chunk_paragraph_start": 1,
        "chunk_paragraph_end": 2,
        "raw_word_count": 8,
        "raw_char_count": 55,
        "scene_paragraph_start": 1,
        "scene_paragraph_end": 2,
        "scene_word_start": 1,
        "scene_word_end": 24,
        "extraction_model": "test-model",
        "refinement_model": "test-model",
        "extracted_at": datetime.now(timezone.utc),
        "props": {},
    }
    data.update(overrides)
    return data


def test_create_get_and_get_by_identity(db: Session) -> None:
    repository = SceneExtractionRepository(db)
    created = repository.create(data=_scene_payload(), commit=True)

    fetched = repository.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id

    identified = repository.get_by_identity(
        book_slug=created.book_slug,
        chapter_number=created.chapter_number,
        scene_number=created.scene_number,
    )
    assert identified is not None
    assert identified.id == created.id

    repository.delete(created, commit=True)


def test_list_for_book_filters_by_chapter(db: Session, scene_factory) -> None:
    repository = SceneExtractionRepository(db)
    slug = f"test-book-list-book-{uuid4()}"

    scene_one = scene_factory(book_slug=slug, chapter_number=1, scene_number=1)
    scene_two = scene_factory(book_slug=slug, chapter_number=2, scene_number=1)
    scene_factory(book_slug=f"test-book-list-other-{uuid4()}")

    for_book = repository.list_for_book(slug)
    assert [scene.id for scene in for_book] == [scene_one.id, scene_two.id]

    chapter_two = repository.list_for_book(slug, chapter_number=2)
    assert [scene.id for scene in chapter_two] == [scene_two.id]


def test_list_unrefined_honors_filters(db: Session, scene_factory) -> None:
    repository = SceneExtractionRepository(db)
    slug = f"test-book-unrefined-{uuid4()}"

    pending = scene_factory(
        book_slug=slug,
        chapter_number=4,
        scene_number=1,
        refinement_decision=None,
        refined=None,
    )
    scene_factory(
        book_slug=slug,
        chapter_number=4,
        scene_number=2,
        refinement_decision="keep",
        refined="Has refinement.",
    )

    unrefined = repository.list_unrefined(
        book_slug=slug,
        chapter_number=4,
        include_refined=False,
    )
    assert [scene.id for scene in unrefined] == [pending.id]

    including_refined = repository.list_unrefined(
        book_slug=slug,
        chapter_number=4,
        include_refined=True,
        limit=1,
    )
    assert len(including_refined) == 1


def test_search_applies_filters_pagination_and_order(
    db: Session, scene_factory
) -> None:
    repository = SceneExtractionRepository(db)
    slug = f"test-book-search-{uuid4()}"
    base_time = datetime(2025, 4, 1, tzinfo=timezone.utc)

    first = scene_factory(
        book_slug=slug,
        chapter_number=1,
        scene_number=1,
        chapter_title="Skyline",
        location_marker="Landing Deck",
        raw="Search target alpha in neon skyline.",
        refined="Search target alpha in neon skyline with glass towers.",
        refinement_decision="keep",
        extracted_at=base_time,
    )
    second = scene_factory(
        book_slug=slug,
        chapter_number=1,
        scene_number=2,
        chapter_title="Harbor",
        location_marker="Dock",
        raw="Search target beta in rainy harbor.",
        refined=None,
        refinement_decision="discard",
        extracted_at=base_time + timedelta(minutes=1),
    )
    scene_factory(
        book_slug=f"test-book-search-other-{uuid4()}",
        chapter_number=9,
        scene_number=1,
        raw="Should be excluded by book filter.",
        extracted_at=base_time + timedelta(minutes=2),
    )

    filtered, total = repository.search(
        page=1,
        page_size=5,
        book_slug=slug,
        chapter_number=1,
        decision="keep",
        has_refined=True,
        search_term="alpha",
        start_date=base_time - timedelta(minutes=1),
        end_date=base_time + timedelta(minutes=1),
        order="asc",
    )
    assert total == 1
    assert [scene.id for scene in filtered] == [first.id]

    ascending, _ = repository.search(
        page=1,
        page_size=10,
        book_slug=slug,
        order="asc",
    )
    assert [scene.id for scene in ascending] == [first.id, second.id]

    page_two, total_for_pagination = repository.search(
        page=2,
        page_size=1,
        book_slug=slug,
        order="asc",
    )
    assert total_for_pagination == 2
    assert [scene.id for scene in page_two] == [second.id]


def test_chunk_indexes_for_chapter_and_filter_options(
    db: Session, scene_factory
) -> None:
    repository = SceneExtractionRepository(db)
    slug_a = f"test-book-options-a-{uuid4()}"
    slug_b = f"test-book-options-b-{uuid4()}"

    first_time = datetime(2025, 5, 1, tzinfo=timezone.utc)
    second_time = datetime(2025, 5, 2, tzinfo=timezone.utc)

    scene_factory(
        book_slug=slug_a,
        chapter_number=6,
        scene_number=1,
        chunk_index=3,
        refinement_decision="keep",
        refined="Refined scene.",
        extracted_at=first_time,
    )
    scene_factory(
        book_slug=slug_a,
        chapter_number=6,
        scene_number=2,
        chunk_index=1,
        refinement_decision=None,
        refined=None,
        extracted_at=second_time,
    )
    scene_factory(
        book_slug=slug_a,
        chapter_number=6,
        scene_number=3,
        chunk_index=3,
        refinement_decision="discard",
        extracted_at=second_time,
    )
    scene_factory(
        book_slug=slug_b,
        chapter_number=2,
        scene_number=1,
        chunk_index=9,
        refinement_decision="keep",
        extracted_at=second_time,
    )

    chunk_indexes = repository.chunk_indexes_for_chapter(
        book_slug=slug_a,
        chapter_number=6,
    )
    assert chunk_indexes == {1, 3}

    options = repository.filter_options()
    books = cast(list[str], options["books"])
    chapters_by_book = cast(dict[str, list[int]], options["chapters_by_book"])
    decisions = cast(list[str], options["refinement_decisions"])
    has_refined_options = cast(list[bool], options["has_refined_options"])
    date_range = cast(dict[str, datetime | None], options["date_range"])

    assert slug_a in books
    assert slug_b in books
    assert chapters_by_book[slug_a] == [6]
    assert chapters_by_book[slug_b] == [2]
    assert "keep" in decisions
    assert "discard" in decisions
    assert set(has_refined_options) == {True, False}
    assert date_range["earliest"] is not None
    assert date_range["latest"] is not None


def test_upsert_update_delete_and_delete_bulk(db: Session) -> None:
    repository = SceneExtractionRepository(db)
    slug = f"test-book-upsert-{uuid4()}"

    created = repository.upsert_by_identity(
        book_slug=slug,
        chapter_number=2,
        scene_number=4,
        values=_scene_payload(book_slug=slug, chapter_number=2, scene_number=4),
        commit=True,
    )
    assert created.book_slug == slug
    assert created.scene_number == 4

    updated = repository.upsert_by_identity(
        book_slug=slug,
        chapter_number=2,
        scene_number=4,
        values={
            "raw": "Updated raw excerpt.",
            "refined": "Updated refined excerpt.",
            "props": {"source": "upsert"},
        },
        commit=True,
    )
    assert updated.id == created.id
    assert updated.raw == "Updated raw excerpt."
    assert updated.props == {"source": "upsert"}

    changed = repository.update(
        updated,
        data={
            "id": uuid4(),
            "chapter_title": "Updated Chapter Title",
            "refinement_decision": "discard",
        },
        commit=True,
    )
    assert changed.id == created.id
    assert changed.chapter_title == "Updated Chapter Title"
    assert changed.refinement_decision == "discard"

    second = repository.create(
        data=_scene_payload(
            book_slug=slug,
            chapter_number=2,
            scene_number=5,
        ),
        commit=True,
    )

    repository.delete(changed, commit=True)
    assert repository.get(changed.id) is None

    repository.delete_bulk([second], commit=True)
    assert repository.get(second.id) is None
