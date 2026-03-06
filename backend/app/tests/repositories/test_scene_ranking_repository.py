"""Tests for SceneRankingRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlmodel import Session

from app.repositories import SceneRankingRepository
from models.scene_extraction import SceneExtraction


def _ranking_payload(
    scene: SceneExtraction,
    *,
    model_name: str,
    prompt_version: str,
    weight_config_hash: str,
    overall_priority: float,
    created_at: datetime | None = None,
) -> dict[str, object]:
    timestamp = created_at or datetime.now(timezone.utc)
    return {
        "scene_extraction_id": scene.id,
        "model_vendor": "google",
        "model_name": model_name,
        "prompt_version": prompt_version,
        "justification": "Repository ranking test.",
        "scores": {"image_prompt_fit": overall_priority},
        "overall_priority": overall_priority,
        "weight_config": {"image_prompt_fit": 1.0},
        "weight_config_hash": weight_config_hash,
        "warnings": [],
        "character_tags": ["Pilot"],
        "raw_response": {"source": "test"},
        "execution_time_ms": 900,
        "temperature": 0.1,
        "llm_request_id": f"req-{uuid4()}",
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def test_create_get_and_get_unique_run(
    db: Session,
    scene_factory,
) -> None:
    repository = SceneRankingRepository(db)
    scene = scene_factory(book_slug=f"test-book-rank-create-{uuid4()}")

    ranking = repository.create(
        data=_ranking_payload(
            scene,
            model_name="rank-model",
            prompt_version="rank-v1",
            weight_config_hash="rank-hash",
            overall_priority=7.0,
        ),
        commit=True,
    )

    fetched = repository.get(ranking.id)
    assert fetched is not None
    assert fetched.id == ranking.id

    unique = repository.get_unique_run(
        scene_extraction_id=scene.id,
        model_name="rank-model",
        prompt_version="rank-v1",
        weight_config_hash="rank-hash",
    )
    assert unique is not None
    assert unique.id == ranking.id

    missing = repository.get_unique_run(
        scene_extraction_id=scene.id,
        model_name="missing",
        prompt_version="rank-v1",
        weight_config_hash="rank-hash",
    )
    assert missing is None


def test_get_latest_for_scene_and_list_for_scene_ordering(
    db: Session,
    scene_factory,
) -> None:
    repository = SceneRankingRepository(db)
    scene = scene_factory(book_slug=f"test-book-rank-history-{uuid4()}")
    base_time = datetime(2025, 6, 1, tzinfo=timezone.utc)

    older = repository.create(
        data=_ranking_payload(
            scene,
            model_name="history-model",
            prompt_version="history-v1",
            weight_config_hash="history-h1",
            overall_priority=3.2,
            created_at=base_time,
        ),
        commit=True,
    )
    newer = repository.create(
        data=_ranking_payload(
            scene,
            model_name="history-model",
            prompt_version="history-v2",
            weight_config_hash="history-h2",
            overall_priority=8.1,
            created_at=base_time + timedelta(minutes=1),
        ),
        commit=True,
    )

    latest = repository.get_latest_for_scene(scene.id)
    assert latest is not None
    assert latest.id == newer.id

    latest_filtered = repository.get_latest_for_scene(
        scene.id,
        model_name="history-model",
        prompt_version="history-v1",
        weight_config_hash="history-h1",
    )
    assert latest_filtered is not None
    assert latest_filtered.id == older.id

    newest_first = repository.list_for_scene(scene.id)
    assert [ranking.id for ranking in newest_first] == [newer.id, older.id]

    oldest_first = repository.list_for_scene(scene.id, newest_first=False)
    assert [ranking.id for ranking in oldest_first] == [older.id, newer.id]

    limited = repository.list_for_scene(scene.id, limit=1)
    assert [ranking.id for ranking in limited] == [newer.id]


def test_top_rankings_ranked_scene_ids_and_global_listing(
    db: Session,
    scene_factory,
) -> None:
    repository = SceneRankingRepository(db)

    slug_a = f"test-book-rank-top-a-{uuid4()}"
    slug_b = f"test-book-rank-top-b-{uuid4()}"
    scene_a1 = scene_factory(book_slug=slug_a)
    scene_a2 = scene_factory(book_slug=slug_a)
    scene_b1 = scene_factory(book_slug=slug_b)

    top_a = repository.create(
        data=_ranking_payload(
            scene_a1,
            model_name="top-model",
            prompt_version="top-v1",
            weight_config_hash="top-h1",
            overall_priority=9.2,
        ),
        commit=True,
    )
    second_a = repository.create(
        data=_ranking_payload(
            scene_a2,
            model_name="top-model",
            prompt_version="top-v1",
            weight_config_hash="top-h1",
            overall_priority=6.8,
        ),
        commit=True,
    )
    global_best = repository.create(
        data=_ranking_payload(
            scene_b1,
            model_name="top-model",
            prompt_version="top-v1",
            weight_config_hash="top-h1",
            overall_priority=9.9,
        ),
        commit=True,
    )

    for_book = repository.list_top_rankings_for_book(
        book_slug=slug_a,
        limit=5,
        model_name="top-model",
        prompt_version="top-v1",
        weight_config_hash="top-h1",
        include_scene=True,
    )
    assert [ranking.id for ranking in for_book] == [top_a.id, second_a.id]
    assert all(ranking.scene_extraction is not None for ranking in for_book)

    ranked_scene_ids = repository.list_ranked_scene_ids_for_book(
        book_slug=slug_a,
        model_name="top-model",
        prompt_version="top-v1",
        weight_config_hash="top-h1",
    )
    assert ranked_scene_ids == {scene_a1.id, scene_a2.id}

    global_top = repository.list_top_rankings(
        limit=2,
        model_name="top-model",
        prompt_version="top-v1",
        weight_config_hash="top-h1",
        include_scene=True,
    )
    assert [ranking.id for ranking in global_top] == [global_best.id, top_a.id]
    assert all(ranking.scene_extraction is not None for ranking in global_top)
