"""Repository helpers for ImageGenerationBatch persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from models.image_generation_batch import ImageGenerationBatch


class ImageGenerationBatchRepository:
    """Provides common queries for working with image generation batches."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def create(
        self,
        *,
        data: Mapping[str, Any],
        commit: bool = False,
        refresh: bool = True,
    ) -> ImageGenerationBatch:
        batch = ImageGenerationBatch(**data)
        self._session.add(batch)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(batch)
        return batch

    def get(self, batch_id: UUID) -> ImageGenerationBatch | None:
        return self._session.get(ImageGenerationBatch, batch_id)

    def get_by_openai_batch_id(
        self, openai_batch_id: str
    ) -> ImageGenerationBatch | None:
        statement = select(ImageGenerationBatch).where(
            ImageGenerationBatch.openai_batch_id == openai_batch_id
        )
        return self._session.exec(statement).first()

    def list_pending(self) -> list[ImageGenerationBatch]:
        """Return batches that are still awaiting completion."""
        statement = (
            select(ImageGenerationBatch)
            .where(
                ImageGenerationBatch.status.in_(
                    ["submitted", "validating", "in_progress"]
                )
            )
            .order_by(ImageGenerationBatch.created_at.asc())
        )
        return list(self._session.exec(statement))

    def update_status(
        self,
        batch_id: UUID,
        status: str,
        **kwargs: Any,
    ) -> ImageGenerationBatch | None:
        """Update batch status and optional fields."""
        batch = self.get(batch_id)
        if batch is None:
            return None
        batch.status = status
        batch.updated_at = datetime.now(timezone.utc)
        for key, value in kwargs.items():
            if hasattr(batch, key):
                setattr(batch, key, value)
        self._session.add(batch)
        self._session.flush()
        self._session.refresh(batch)
        return batch
