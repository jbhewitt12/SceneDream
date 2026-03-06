"""Tests for scene ranking API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.repositories import SceneRankingRepository
from models.scene_extraction import SceneExtraction


def _ranking_payload(
    scene: SceneExtraction,
    *,
    overall_priority: float,
    model_name: str = "rank-model",
    prompt_version: str = "ranking-v1",
    weight_config_hash: str = "hash-v1",
    created_at: datetime | None = None,
) -> dict[str, object]:
    now = created_at or datetime.now(timezone.utc)
    return {
        "scene_extraction_id": scene.id,
        "model_vendor": "google",
        "model_name": model_name,
        "prompt_version": prompt_version,
        "justification": "Strong cinematic composition.",
        "scores": {"image_prompt_fit": overall_priority},
        "overall_priority": overall_priority,
        "weight_config": {"image_prompt_fit": 1.0},
        "weight_config_hash": weight_config_hash,
        "warnings": [],
        "character_tags": ["Lead"],
        "raw_response": {"ok": True},
        "execution_time_ms": 1250,
        "temperature": 0.2,
        "llm_request_id": f"req-{uuid4()}",
        "created_at": now,
        "updated_at": now,
    }


def test_list_top_scene_rankings_supports_filters(
    client: TestClient,
    db: Session,
    scene_factory,
) -> None:
    ranking_repo = SceneRankingRepository(db)

    scene_a = scene_factory(book_slug=f"test-book-rankings-a-{uuid4()}")
    scene_b = scene_factory(book_slug=f"test-book-rankings-b-{uuid4()}")

    ranking_repo.create(
        data=_ranking_payload(
            scene_a,
            overall_priority=9.5,
            model_name="rank-model",
            prompt_version="ranking-v1",
            weight_config_hash="hash-1",
        ),
        commit=True,
    )
    ranking_repo.create(
        data=_ranking_payload(
            scene_a,
            overall_priority=7.0,
            model_name="other-model",
            prompt_version="ranking-v2",
            weight_config_hash="hash-2",
        ),
        commit=True,
    )
    ranking_repo.create(
        data=_ranking_payload(
            scene_b,
            overall_priority=8.8,
            model_name="rank-model",
            prompt_version="ranking-v1",
            weight_config_hash="hash-1",
        ),
        commit=True,
    )

    top_response = client.get("/api/v1/scene-rankings/top", params={"limit": 1})
    assert top_response.status_code == 200
    top_payload = top_response.json()
    assert top_payload["meta"]["limit"] == 1
    assert top_payload["meta"]["count"] == 1

    filtered_response = client.get(
        "/api/v1/scene-rankings/top",
        params={
            "book_slug": scene_a.book_slug,
            "limit": 10,
            "model_name": "rank-model",
            "prompt_version": "ranking-v1",
            "weight_config_hash": "hash-1",
            "include_scene": True,
        },
    )

    assert filtered_response.status_code == 200
    filtered_payload = filtered_response.json()
    assert filtered_payload["meta"]["book_slug"] == scene_a.book_slug
    assert filtered_payload["meta"]["model_name"] == "rank-model"
    assert filtered_payload["meta"]["prompt_version"] == "ranking-v1"
    assert filtered_payload["meta"]["weight_config_hash"] == "hash-1"
    assert len(filtered_payload["data"]) == 1
    assert filtered_payload["data"][0]["scene_extraction_id"] == str(scene_a.id)
    assert filtered_payload["data"][0]["scene"]["id"] == str(scene_a.id)


def test_list_scene_ranking_history_and_scene_not_found(
    client: TestClient,
    db: Session,
    scene_factory,
) -> None:
    ranking_repo = SceneRankingRepository(db)
    scene = scene_factory(book_slug=f"test-book-history-{uuid4()}")

    base_time = datetime(2025, 3, 1, tzinfo=timezone.utc)
    older = ranking_repo.create(
        data=_ranking_payload(
            scene,
            overall_priority=4.0,
            model_name="history-model",
            prompt_version="v1",
            weight_config_hash="history-1",
            created_at=base_time,
        ),
        commit=True,
    )
    newer = ranking_repo.create(
        data=_ranking_payload(
            scene,
            overall_priority=6.0,
            model_name="history-model",
            prompt_version="v2",
            weight_config_hash="history-2",
            created_at=base_time + timedelta(minutes=1),
        ),
        commit=True,
    )

    response = client.get(
        f"/api/v1/scene-rankings/scene/{scene.id}",
        params={"limit": 1, "newest_first": False, "include_scene": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["scene_extraction_id"] == str(scene.id)
    assert payload["meta"]["count"] == 1
    assert payload["meta"]["newest_first"] is False
    assert payload["meta"]["scene"]["id"] == str(scene.id)
    assert [item["id"] for item in payload["data"]] == [str(older.id)]
    assert str(newer.id) != payload["data"][0]["id"]

    missing_response = client.get(f"/api/v1/scene-rankings/scene/{uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Scene extraction not found"


def test_get_scene_ranking_by_id_and_not_found(
    client: TestClient,
    db: Session,
    scene_factory,
) -> None:
    ranking_repo = SceneRankingRepository(db)
    scene = scene_factory(book_slug=f"test-book-get-ranking-{uuid4()}")
    ranking = ranking_repo.create(
        data=_ranking_payload(
            scene,
            overall_priority=5.5,
            model_name="get-model",
            prompt_version="get-v1",
            weight_config_hash="get-hash",
        ),
        commit=True,
    )

    response = client.get(
        f"/api/v1/scene-rankings/{ranking.id}",
        params={"include_scene": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(ranking.id)
    assert payload["scene_extraction_id"] == str(scene.id)
    assert payload["scene"]["id"] == str(scene.id)

    missing_response = client.get(f"/api/v1/scene-rankings/{uuid4()}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Scene ranking not found"
