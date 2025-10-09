"""Repository helpers for ImagePrompt persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.orm import joinedload
from sqlmodel import Session, select

from models.image_prompt import ImagePrompt
from models.scene_extraction import SceneExtraction


class ImagePromptRepository:
    """Provides common queries for working with image prompts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, prompt_id: UUID) -> ImagePrompt | None:
        return self._session.get(ImagePrompt, prompt_id)

    def list_for_scene(
        self,
        scene_extraction_id: UUID,
        *,
        model_name: str | None = None,
        prompt_version: str | None = None,
        newest_first: bool = True,
        limit: int | None = None,
    ) -> list[ImagePrompt]:
        statement = select(ImagePrompt).where(
            ImagePrompt.scene_extraction_id == scene_extraction_id
        )
        if model_name:
            statement = statement.where(ImagePrompt.model_name == model_name)
        if prompt_version:
            statement = statement.where(ImagePrompt.prompt_version == prompt_version)
        ordering = (
            ImagePrompt.created_at.desc()
            if newest_first
            else ImagePrompt.created_at.asc()
        )
        statement = statement.order_by(ordering, ImagePrompt.variant_index.asc())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def list_for_book(
        self,
        *,
        book_slug: str,
        model_name: str | None = None,
        prompt_version: str | None = None,
        style_tag: str | None = None,
        chapter_number: int | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        include_scene: bool = False,
    ) -> list[ImagePrompt]:
        statement = (
            select(ImagePrompt)
            .join(
                SceneExtraction,
                ImagePrompt.scene_extraction_id == SceneExtraction.id,
            )
            .where(SceneExtraction.book_slug == book_slug)
        )
        if model_name:
            statement = statement.where(ImagePrompt.model_name == model_name)
        if prompt_version:
            statement = statement.where(ImagePrompt.prompt_version == prompt_version)
        if style_tag:
            statement = statement.where(ImagePrompt.style_tags.contains([style_tag]))
        if chapter_number is not None:
            statement = statement.where(
                SceneExtraction.chapter_number == chapter_number
            )
        ordering = (
            ImagePrompt.created_at.desc()
            if newest_first
            else ImagePrompt.created_at.asc()
        )
        statement = statement.order_by(ordering, ImagePrompt.variant_index.asc())
        if include_scene:
            statement = statement.options(joinedload(ImagePrompt.scene_extraction))
        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def get_latest_set_for_scene(
        self, scene_extraction_id: UUID, model_name: str, prompt_version: str
    ) -> list[ImagePrompt]:
        statement = select(ImagePrompt).where(
            ImagePrompt.scene_extraction_id == scene_extraction_id,
            ImagePrompt.model_name == model_name,
            ImagePrompt.prompt_version == prompt_version,
        )
        statement = statement.order_by(ImagePrompt.variant_index.asc())
        return list(self._session.exec(statement))

    def create(
        self,
        *,
        data: Mapping[str, Any],
        commit: bool = False,
        refresh: bool = True,
    ) -> ImagePrompt:
        prompt = ImagePrompt(**data)  # type: ignore[arg-type]
        self._session.add(prompt)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(prompt)
        return prompt

    def bulk_create(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        commit: bool = False,
        refresh: bool = True,
    ) -> list[ImagePrompt]:
        prompts = [ImagePrompt(**record) for record in records]
        self._session.add_all(prompts)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            for prompt in prompts:
                self._session.refresh(prompt)
        return prompts

    def delete_for_scene(
        self,
        scene_extraction_id: UUID,
        *,
        prompt_version: str | None = None,
        model_name: str | None = None,
        commit: bool = False,
    ) -> int:
        statement = delete(ImagePrompt).where(
            ImagePrompt.scene_extraction_id == scene_extraction_id
        )
        if prompt_version:
            statement = statement.where(ImagePrompt.prompt_version == prompt_version)
        if model_name:
            statement = statement.where(ImagePrompt.model_name == model_name)
        result = self._session.execute(statement)
        if commit:
            self._session.commit()
        return int(result.rowcount or 0)
