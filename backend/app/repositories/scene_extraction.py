"""Repository helpers for SceneExtraction persistence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Mapping, Optional
from uuid import UUID

from sqlalchemy import and_, func, or_
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

    def list_unrefined(
        self,
        *,
        book_slug: Optional[str] = None,
        chapter_number: Optional[int] = None,
        limit: Optional[int] = None,
        include_refined: bool = False,
    ) -> list[SceneExtraction]:
        statement = select(SceneExtraction)
        if not include_refined:
            statement = statement.where(SceneExtraction.refinement_decision.is_(None))
        if book_slug:
            statement = statement.where(SceneExtraction.book_slug == book_slug)
        if chapter_number is not None:
            statement = statement.where(SceneExtraction.chapter_number == chapter_number)
        statement = statement.order_by(
            SceneExtraction.book_slug,
            SceneExtraction.chapter_number,
            SceneExtraction.scene_number,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def search(
        self,
        *,
        page: int,
        page_size: int,
        book_slug: str | None = None,
        chapter_number: int | None = None,
        decision: str | None = None,
        has_refined: bool | None = None,
        search_term: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        order: str = "desc",
    ) -> tuple[list[SceneExtraction], int]:
        filters = []

        if book_slug:
            filters.append(SceneExtraction.book_slug == book_slug)
        if chapter_number is not None:
            filters.append(SceneExtraction.chapter_number == chapter_number)
        if decision:
            filters.append(SceneExtraction.refinement_decision == decision)
        if has_refined is not None:
            if has_refined:
                filters.append(SceneExtraction.refined.is_not(None))
            else:
                filters.append(SceneExtraction.refined.is_(None))
        if start_date:
            filters.append(SceneExtraction.extracted_at >= start_date)
        if end_date:
            filters.append(SceneExtraction.extracted_at <= end_date)

        statement = select(SceneExtraction)
        count_statement = select(func.count()).select_from(SceneExtraction)

        if search_term:
            pattern = f"%{search_term.strip()}%"
            search_filter = or_(
                SceneExtraction.chapter_title.ilike(pattern),
                SceneExtraction.location_marker.ilike(pattern),
                SceneExtraction.raw.ilike(pattern),
                SceneExtraction.refined.ilike(pattern),
            )
            filters.append(search_filter)

        if filters:
            statement = statement.where(and_(*filters))
            count_statement = count_statement.where(and_(*filters))

        ordering = (
            SceneExtraction.extracted_at.asc()
            if order.lower() == "asc"
            else SceneExtraction.extracted_at.desc()
        )

        statement = statement.order_by(ordering)
        statement = statement.offset((page - 1) * page_size).limit(page_size)

        records = list(self._session.exec(statement))
        total = self._session.exec(count_statement).one()
        return records, int(total)

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

    def filter_options(self) -> dict[str, object]:
        book_statement = (
            select(SceneExtraction.book_slug)
            .distinct()
            .order_by(SceneExtraction.book_slug)
        )
        book_slugs = [value for value in self._session.exec(book_statement).all() if value]

        chapter_statement = (
            select(SceneExtraction.book_slug, SceneExtraction.chapter_number)
            .distinct()
        )
        chapters_by_book: dict[str, list[int]] = defaultdict(list)
        for book, chapter in self._session.exec(chapter_statement).all():
            if book is None or chapter is None:
                continue
            chapters_by_book[book].append(int(chapter))

        for chapter_list in chapters_by_book.values():
            chapter_list.sort()

        decisions_statement = (
            select(SceneExtraction.refinement_decision)
            .distinct()
            .order_by(SceneExtraction.refinement_decision)
        )
        decisions = [value for value in self._session.exec(decisions_statement).all() if value]

        earliest = self._session.exec(
            select(func.min(SceneExtraction.extracted_at))
        ).one()
        latest = self._session.exec(
            select(func.max(SceneExtraction.extracted_at))
        ).one()

        has_refined_options: list[bool] = []
        refined_count = self._session.exec(
            select(func.count())
            .select_from(SceneExtraction)
            .where(SceneExtraction.refined.is_not(None))
        ).one()
        if refined_count:
            has_refined_options.append(True)
        unrefined_count = self._session.exec(
            select(func.count())
            .select_from(SceneExtraction)
            .where(SceneExtraction.refined.is_(None))
        ).one()
        if unrefined_count:
            has_refined_options.append(False)

        return {
            "books": book_slugs,
            "chapters_by_book": dict(chapters_by_book),
            "refinement_decisions": decisions,
            "has_refined_options": has_refined_options,
            "date_range": {
                "earliest": earliest,
                "latest": latest,
            },
        }

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
