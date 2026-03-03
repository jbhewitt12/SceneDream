"""Repository helpers for Document persistence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from models.document import Document


class DocumentRepository:
    """Provides common queries and mutations for canonical documents."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, document_id: UUID) -> Document | None:
        return self._session.get(Document, document_id)

    def get_by_slug(self, slug: str) -> Document | None:
        statement = select(Document).where(Document.slug == slug)
        return self._session.exec(statement).first()

    def list(
        self,
        *,
        source_type: str | None = None,
        ingestion_state: str | None = None,
        newest_first: bool = True,
        limit: int | None = None,
    ) -> list[Document]:
        statement = select(Document)
        if source_type:
            statement = statement.where(Document.source_type == source_type)
        if ingestion_state:
            statement = statement.where(Document.ingestion_state == ingestion_state)

        ordering = (
            Document.created_at.desc() if newest_first else Document.created_at.asc()
        )
        statement = statement.order_by(ordering)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> Document:
        document = Document(**data)
        self._session.add(document)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(document)
        return document

    def update(
        self,
        document: Document,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> Document:
        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(document, key):
                setattr(document, key, value)
        document.updated_at = datetime.now(timezone.utc)
        self._session.add(document)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(document)
        return document

    def upsert_by_slug(
        self,
        *,
        slug: str,
        values: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> Document:
        document = self.get_by_slug(slug)
        payload = dict(values)
        payload.setdefault("slug", slug)
        if document is None:
            return self.create(data=payload, commit=commit, refresh=refresh)
        return self.update(document, data=payload, commit=commit, refresh=refresh)
