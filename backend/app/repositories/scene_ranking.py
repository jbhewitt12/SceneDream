"""Repository helpers for SceneRanking persistence."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.orm import joinedload
from sqlmodel import Session, select

from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking


class SceneRankingRepository:
    """Provides common queries for working with scene rankings."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, ranking_id: UUID) -> SceneRanking | None:
        return self._session.get(SceneRanking, ranking_id)

    def get_unique_run(
        self,
        *,
        scene_extraction_id: UUID,
        model_name: str,
        prompt_version: str,
        weight_config_hash: str,
    ) -> SceneRanking | None:
        statement = select(SceneRanking).where(
            SceneRanking.scene_extraction_id == scene_extraction_id,
            SceneRanking.model_name == model_name,
            SceneRanking.prompt_version == prompt_version,
            SceneRanking.weight_config_hash == weight_config_hash,
        )
        return self._session.exec(statement).first()

    def get_latest_for_scene(
        self,
        scene_extraction_id: UUID,
        *,
        model_name: str | None = None,
        prompt_version: str | None = None,
        weight_config_hash: str | None = None,
    ) -> SceneRanking | None:
        statement = select(SceneRanking).where(
            SceneRanking.scene_extraction_id == scene_extraction_id
        )
        if model_name:
            statement = statement.where(SceneRanking.model_name == model_name)
        if prompt_version:
            statement = statement.where(SceneRanking.prompt_version == prompt_version)
        if weight_config_hash:
            statement = statement.where(
                SceneRanking.weight_config_hash == weight_config_hash
            )
        statement = statement.order_by(SceneRanking.created_at.desc())
        return self._session.exec(statement).first()

    def list_for_scene(
        self,
        scene_extraction_id: UUID,
        *,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[SceneRanking]:
        statement = select(SceneRanking).where(
            SceneRanking.scene_extraction_id == scene_extraction_id
        )
        ordering = (
            SceneRanking.created_at.desc()
            if newest_first
            else SceneRanking.created_at.asc()
        )
        statement = statement.order_by(ordering)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def list_top_rankings_for_book(
        self,
        *,
        book_slug: str,
        limit: int = 10,
        model_name: str | None = None,
        prompt_version: str | None = None,
        weight_config_hash: str | None = None,
        include_scene: bool = False,
    ) -> list[SceneRanking]:
        statement = (
            select(SceneRanking)
            .join(
                SceneExtraction, SceneRanking.scene_extraction_id == SceneExtraction.id
            )
            .where(SceneExtraction.book_slug == book_slug)
            .order_by(
                SceneRanking.overall_priority.desc(),
                SceneRanking.created_at.desc(),
            )
        )
        if model_name:
            statement = statement.where(SceneRanking.model_name == model_name)
        if prompt_version:
            statement = statement.where(SceneRanking.prompt_version == prompt_version)
        if weight_config_hash:
            statement = statement.where(
                SceneRanking.weight_config_hash == weight_config_hash
            )
        if include_scene:
            statement = statement.options(joinedload(SceneRanking.scene_extraction))
        statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def list_ranked_scene_ids_for_book(
        self,
        *,
        book_slug: str,
        model_name: str,
        prompt_version: str,
        weight_config_hash: str,
    ) -> set[UUID]:
        statement = (
            select(SceneRanking.scene_extraction_id)
            .join(
                SceneExtraction, SceneRanking.scene_extraction_id == SceneExtraction.id
            )
            .where(SceneExtraction.book_slug == book_slug)
            .where(SceneRanking.model_name == model_name)
            .where(SceneRanking.prompt_version == prompt_version)
            .where(SceneRanking.weight_config_hash == weight_config_hash)
        )
        records = self._session.exec(statement).all()
        ranked: set[UUID] = set()
        for record in records:
            if record is None:
                continue
            if isinstance(record, UUID):
                ranked.add(record)
                continue
            if isinstance(record, tuple):
                candidate = record[0] if record else None
                if isinstance(candidate, UUID):
                    ranked.add(candidate)
            else:
                try:
                    candidate = UUID(str(record))
                except Exception:
                    continue
                ranked.add(candidate)
        return ranked

    def list_top_rankings(
        self,
        *,
        limit: int = 10,
        model_name: str | None = None,
        prompt_version: str | None = None,
        weight_config_hash: str | None = None,
        include_scene: bool = False,
    ) -> list[SceneRanking]:
        """Return globally top rankings across all books by overall_priority."""
        statement = (
            select(SceneRanking)
            .join(
                SceneExtraction, SceneRanking.scene_extraction_id == SceneExtraction.id
            )
            .order_by(
                SceneRanking.overall_priority.desc(),
                SceneRanking.created_at.desc(),
            )
        )
        if model_name:
            statement = statement.where(SceneRanking.model_name == model_name)
        if prompt_version:
            statement = statement.where(SceneRanking.prompt_version == prompt_version)
        if weight_config_hash:
            statement = statement.where(
                SceneRanking.weight_config_hash == weight_config_hash
            )
        if include_scene:
            statement = statement.options(joinedload(SceneRanking.scene_extraction))
        statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SceneRanking:
        ranking = SceneRanking(**data)
        self._session.add(ranking)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(ranking)
        return ranking
