"""Repository helpers for GeneratedImage persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import distinct
from sqlalchemy.orm import joinedload
from sqlmodel import Session, select

from models.generated_image import GeneratedImage
from models.social_media_post import SocialMediaPost


class GeneratedImageRepository:
    """Provides common queries for working with generated images."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, image_id: UUID) -> GeneratedImage | None:
        return self._session.get(GeneratedImage, image_id)

    def create(
        self,
        *,
        data: Mapping[str, Any],
        commit: bool = False,
        refresh: bool = True,
    ) -> GeneratedImage:
        image = GeneratedImage(**data)
        self._session.add(image)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(image)
        return image

    def bulk_create(
        self,
        records: Sequence[Mapping[str, Any]],
        *,
        commit: bool = False,
        refresh: bool = True,
    ) -> list[GeneratedImage]:
        images = [GeneratedImage(**record) for record in records]
        self._session.add_all(images)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            for image in images:
                self._session.refresh(image)
        return images

    def list_for_scene(
        self,
        scene_extraction_id: UUID,
        *,
        provider: str | None = None,
        model: str | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        include_prompt: bool = False,
        include_scene: bool = False,
        include_posting_status: bool = False,
    ) -> list[GeneratedImage]:
        statement = select(GeneratedImage).where(
            GeneratedImage.scene_extraction_id == scene_extraction_id
        )
        if provider:
            statement = statement.where(GeneratedImage.provider == provider)
        if model:
            statement = statement.where(GeneratedImage.model == model)

        ordering = (
            GeneratedImage.created_at.desc()
            if newest_first
            else GeneratedImage.created_at.asc()
        )
        statement = statement.order_by(ordering, GeneratedImage.variant_index.asc())

        if include_prompt:
            statement = statement.options(joinedload(GeneratedImage.image_prompt))
        if include_scene:
            statement = statement.options(joinedload(GeneratedImage.scene_extraction))
        if include_posting_status:
            statement = statement.options(joinedload(GeneratedImage.social_media_posts))

        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        result = self._session.exec(statement)
        if include_posting_status:
            result = result.unique()
        return list(result)

    def list_for_book(
        self,
        book_slug: str,
        *,
        chapter_number: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        approval: bool | None = None,
        posted: bool | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        include_prompt: bool = False,
        include_scene: bool = False,
        include_posting_status: bool = False,
    ) -> list[GeneratedImage]:
        statement = select(GeneratedImage).where(GeneratedImage.book_slug == book_slug)

        if chapter_number is not None:
            statement = statement.where(GeneratedImage.chapter_number == chapter_number)
        if provider:
            statement = statement.where(GeneratedImage.provider == provider)
        if model:
            statement = statement.where(GeneratedImage.model == model)
        if approval is not None:
            statement = statement.where(GeneratedImage.user_approved == approval)

        # Filter by posting status
        if posted is True:
            # Has at least one post with status="posted"
            posted_subquery = (
                select(SocialMediaPost.generated_image_id)
                .where(SocialMediaPost.status == "posted")
                .distinct()
            )
            statement = statement.where(GeneratedImage.id.in_(posted_subquery))
        elif posted is False:
            # Has no posts with status="posted"
            posted_subquery = (
                select(SocialMediaPost.generated_image_id)
                .where(SocialMediaPost.status == "posted")
                .distinct()
            )
            statement = statement.where(GeneratedImage.id.notin_(posted_subquery))

        ordering = (
            GeneratedImage.created_at.desc()
            if newest_first
            else GeneratedImage.created_at.asc()
        )
        statement = statement.order_by(ordering)

        if include_prompt:
            statement = statement.options(joinedload(GeneratedImage.image_prompt))
        if include_scene:
            statement = statement.options(joinedload(GeneratedImage.scene_extraction))
        if include_posting_status:
            statement = statement.options(joinedload(GeneratedImage.social_media_posts))

        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        result = self._session.exec(statement)
        if include_posting_status:
            result = result.unique()
        return list(result)

    def list_all(
        self,
        *,
        chapter_number: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        approval: bool | None = None,
        posted: bool | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        include_prompt: bool = False,
        include_scene: bool = False,
        include_posting_status: bool = False,
    ) -> list[GeneratedImage]:
        """Return generated images across all books with optional filters."""

        statement = select(GeneratedImage)

        if chapter_number is not None:
            statement = statement.where(GeneratedImage.chapter_number == chapter_number)
        if provider:
            statement = statement.where(GeneratedImage.provider == provider)
        if model:
            statement = statement.where(GeneratedImage.model == model)
        if approval is not None:
            statement = statement.where(GeneratedImage.user_approved == approval)

        # Filter by posting status
        if posted is True:
            # Has at least one post with status="posted"
            posted_subquery = (
                select(SocialMediaPost.generated_image_id)
                .where(SocialMediaPost.status == "posted")
                .distinct()
            )
            statement = statement.where(GeneratedImage.id.in_(posted_subquery))
        elif posted is False:
            # Has no posts with status="posted"
            posted_subquery = (
                select(SocialMediaPost.generated_image_id)
                .where(SocialMediaPost.status == "posted")
                .distinct()
            )
            statement = statement.where(GeneratedImage.id.notin_(posted_subquery))

        ordering = (
            GeneratedImage.created_at.desc()
            if newest_first
            else GeneratedImage.created_at.asc()
        )
        statement = statement.order_by(ordering)

        if include_prompt:
            statement = statement.options(joinedload(GeneratedImage.image_prompt))
        if include_scene:
            statement = statement.options(joinedload(GeneratedImage.scene_extraction))
        if include_posting_status:
            statement = statement.options(joinedload(GeneratedImage.social_media_posts))

        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        result = self._session.exec(statement)
        if include_posting_status:
            result = result.unique()
        return list(result)

    def list_for_prompt(
        self,
        image_prompt_id: UUID,
        *,
        provider: str | None = None,
        model: str | None = None,
        newest_first: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        include_prompt: bool = False,
        include_scene: bool = False,
        include_posting_status: bool = False,
    ) -> list[GeneratedImage]:
        statement = select(GeneratedImage).where(
            GeneratedImage.image_prompt_id == image_prompt_id
        )

        if provider:
            statement = statement.where(GeneratedImage.provider == provider)
        if model:
            statement = statement.where(GeneratedImage.model == model)

        ordering = (
            GeneratedImage.created_at.desc()
            if newest_first
            else GeneratedImage.created_at.asc()
        )
        statement = statement.order_by(ordering)

        if include_prompt:
            statement = statement.options(joinedload(GeneratedImage.image_prompt))
        if include_scene:
            statement = statement.options(joinedload(GeneratedImage.scene_extraction))
        if include_posting_status:
            statement = statement.options(joinedload(GeneratedImage.social_media_posts))

        if offset is not None:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        result = self._session.exec(statement)
        if include_posting_status:
            result = result.unique()
        return list(result)

    def get_latest_for_prompt(
        self,
        image_prompt_id: UUID,
        *,
        variant_index: int = 0,
        provider: str = "openai",
        model: str = "dall-e-3",
    ) -> GeneratedImage | None:
        """Get the most recently created image for a specific prompt configuration."""
        statement = (
            select(GeneratedImage)
            .where(
                GeneratedImage.image_prompt_id == image_prompt_id,
                GeneratedImage.variant_index == variant_index,
                GeneratedImage.provider == provider,
                GeneratedImage.model == model,
            )
            .order_by(GeneratedImage.created_at.desc())
            .limit(1)
        )
        return self._session.exec(statement).first()

    def find_existing_by_params(
        self,
        image_prompt_id: UUID,
        variant_index: int,
        provider: str,
        model: str,
        size: str,
        quality: str,
        style: str,
    ) -> GeneratedImage | None:
        """
        Find an existing image matching the idempotency constraint parameters.
        Returns None if no match exists, enabling safe duplicate detection.
        """
        statement = select(GeneratedImage).where(
            GeneratedImage.image_prompt_id == image_prompt_id,
            GeneratedImage.variant_index == variant_index,
            GeneratedImage.provider == provider,
            GeneratedImage.model == model,
            GeneratedImage.size == size,
            GeneratedImage.quality == quality,
            GeneratedImage.style == style,
        )
        return self._session.exec(statement).first()

    def mark_failed(
        self,
        image_id: UUID,
        error: str,
        *,
        commit: bool = False,
    ) -> GeneratedImage | None:
        """Mark an image generation as failed with an error message."""
        image = self.get(image_id)
        if image:
            image.error = error
            self._session.add(image)
            self._session.flush()
            if commit:
                self._session.commit()
            self._session.refresh(image)
        return image

    def update_approval(
        self,
        image_id: UUID,
        approved: bool | None,
        *,
        commit: bool = False,
    ) -> GeneratedImage | None:
        """Update the approval status of a generated image."""

        image = self.get(image_id)
        if image:
            current_time = datetime.now(timezone.utc)
            image.user_approved = approved
            image.approval_updated_at = current_time
            self._session.add(image)
            self._session.flush()
            if commit:
                self._session.commit()
            self._session.refresh(image)
        return image

    def get_distinct_providers(self) -> list[str]:
        """Return list of distinct provider values from all generated images."""
        statement = select(distinct(GeneratedImage.provider)).where(
            GeneratedImage.provider.isnot(None)
        )
        result = self._session.exec(statement)
        return [provider for provider in result if provider is not None]
