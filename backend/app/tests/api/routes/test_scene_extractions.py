"""Tests for scene extraction API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient


def test_list_scene_extractions_applies_filters_and_pagination(
    client: TestClient,
    scene_factory,
) -> None:
    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    matching_scene = scene_factory(
        book_slug=f"test-book-scenes-{uuid4()}",
        chapter_number=3,
        scene_number=1,
        chapter_title="Sky Harbor",
        location_marker="Docking Bay 7",
        raw="Neon skyline glows above the harbor.",
        refined="Neon skyline glows above the harbor while ships descend.",
        refinement_decision="keep",
        extracted_at=base_time,
    )
    scene_factory(
        book_slug=matching_scene.book_slug,
        chapter_number=3,
        scene_number=2,
        raw="A maintenance drone drifts past the bay doors.",
        refined=None,
        refinement_decision="discard",
        extracted_at=base_time + timedelta(minutes=1),
    )
    scene_factory(
        book_slug=f"test-book-other-{uuid4()}",
        chapter_number=9,
        scene_number=1,
        raw="Unrelated scene that should not match filters.",
        refined="Unrelated scene refined.",
        refinement_decision="keep",
        extracted_at=base_time + timedelta(minutes=2),
    )

    response = client.get(
        "/api/v1/scene-extractions/",
        params={
            "page": 1,
            "page_size": 10,
            "book_slug": matching_scene.book_slug,
            "chapter_number": 3,
            "decision": "keep",
            "has_refined": True,
            "search": "skyline",
            "start_date": (base_time - timedelta(minutes=1)).isoformat(),
            "end_date": (base_time + timedelta(minutes=1)).isoformat(),
            "order": "asc",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 10
    assert [item["id"] for item in payload["data"]] == [str(matching_scene.id)]


def test_scene_extraction_filters_returns_expected_options(
    client: TestClient,
    scene_factory,
) -> None:
    first_time = datetime(2025, 2, 1, tzinfo=timezone.utc)
    second_time = datetime(2025, 2, 2, tzinfo=timezone.utc)

    first = scene_factory(
        book_slug=f"test-book-filters-a-{uuid4()}",
        chapter_number=2,
        scene_number=1,
        refinement_decision="keep",
        refined="A calm orbiting station.",
        extracted_at=first_time,
    )
    second = scene_factory(
        book_slug=f"test-book-filters-b-{uuid4()}",
        chapter_number=4,
        scene_number=1,
        refinement_decision="discard",
        refined=None,
        extracted_at=second_time,
    )

    response = client.get("/api/v1/scene-extractions/filters")

    assert response.status_code == 200
    payload = response.json()
    assert first.book_slug in payload["books"]
    assert second.book_slug in payload["books"]
    assert payload["chapters_by_book"][first.book_slug] == [2]
    assert payload["chapters_by_book"][second.book_slug] == [4]
    assert "keep" in payload["refinement_decisions"]
    assert "discard" in payload["refinement_decisions"]
    assert set(payload["has_refined_options"]) == {True, False}
    assert payload["date_range"]["earliest"] is not None
    assert payload["date_range"]["latest"] is not None


def test_get_scene_extraction_by_id_and_not_found(
    client: TestClient,
    scene_factory,
) -> None:
    scene = scene_factory(chapter_title="Route Read Test")

    response = client.get(f"/api/v1/scene-extractions/{scene.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(scene.id)
    assert payload["chapter_title"] == "Route Read Test"

    missing_response = client.get(f"/api/v1/scene-extractions/{uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Scene extraction not found"
