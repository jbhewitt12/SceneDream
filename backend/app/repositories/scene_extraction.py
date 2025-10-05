"""Repository helpers for SceneExtraction persistence."""

from __future__ import annotations

from typing import Iterable, Mapping, Optional
from uuid import UUID

from sqlmodel import Session, select

from models.scene_extraction import SceneExtraction


class SceneExtractionRepository:
    """Contains common queries and mutations for scene extractions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, scene_id: UUID) -> SceneExtraction | None:
        return self._session.get(SceneExtraction, scene_id)

    def get_by_identity(
        self,
        *,
        book_slug: str,
        chapter_number: int,
        scene_number: int,
    ) -> SceneExtraction | None:
        statement = select(SceneExtraction).where(
            SceneExtraction.book_slug == book_slug,
            SceneExtraction.chapter_number == chapter_number,
            SceneExtraction.scene_number == scene_number,
        )
        return self._session.exec(statement).first()

    def list_for_book(
        self,
        book_slug: str,
        *,
        chapter_number: Optional[int] = None,
    ) -> list[SceneExtraction]:
        statement = select(SceneExtraction).where(SceneExtraction.book_slug == book_slug)
        if chapter_number is not None:
            statement = statement.where(SceneExtraction.chapter_number == chapter_number)
        statement = statement.order_by(
            SceneExtraction.chapter_number,
            SceneExtraction.scene_number,
        )
        return list(self._session.exec(statement))

    def chunk_indexes_for_chapter(
        self,
        *,
        book_slug: str,
        chapter_number: int,
    ) -> set[int]:
        statement = (
            select(SceneExtraction.chunk_index)
            .where(
                SceneExtraction.book_slug == book_slug,
                SceneExtraction.chapter_number == chapter_number,
            )
            .distinct()
        )
        result = self._session.exec(statement).all()
        return {value for value in result if isinstance(value, int)}

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SceneExtraction:
        scene = SceneExtraction(**data)
        self._session.add(scene)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(scene)
        return scene

    def update(
        self,
        scene: SceneExtraction,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SceneExtraction:
        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(scene, key):
                setattr(scene, key, value)
        self._session.add(scene)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(scene)
        return scene

    def upsert_by_identity(
        self,
        *,
        book_slug: str,
        chapter_number: int,
        scene_number: int,
        values: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> SceneExtraction:
        record = self.get_by_identity(
            book_slug=book_slug,
            chapter_number=chapter_number,
            scene_number=scene_number,
        )
        payload = dict(values)
        payload.setdefault("book_slug", book_slug)
        payload.setdefault("chapter_number", chapter_number)
        payload.setdefault("scene_number", scene_number)
        if record is None:
            return self.create(data=payload, commit=commit, refresh=refresh)
        return self.update(record, data=payload, commit=commit, refresh=refresh)

    def delete(
        self,
        scene: SceneExtraction,
        *,
        commit: bool = False,
    ) -> None:
        self._session.delete(scene)
        if commit:
            self._session.commit()

    def delete_bulk(
        self,
        scenes: Iterable[SceneExtraction],
        *,
        commit: bool = False,
    ) -> None:
        for scene in scenes:
            self._session.delete(scene)
        self._session.flush()
        if commit:
            self._session.commit()

