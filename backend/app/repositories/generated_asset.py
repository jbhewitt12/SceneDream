"""Repository helpers for GeneratedAsset persistence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, select

from models.generated_asset import GeneratedAsset


class GeneratedAssetRepository:
    """Provides common queries and mutations for generated assets."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session

    def get(self, asset_id: UUID) -> GeneratedAsset | None:
        return self._session.get(GeneratedAsset, asset_id)

    def create(
        self,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> GeneratedAsset:
        asset = GeneratedAsset(**data)
        self._session.add(asset)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(asset)
        return asset

    def bulk_create(
        self,
        records: Sequence[Mapping[str, object]],
        *,
        commit: bool = False,
        refresh: bool = True,
    ) -> list[GeneratedAsset]:
        assets = [GeneratedAsset(**record) for record in records]
        self._session.add_all(assets)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            for asset in assets:
                self._session.refresh(asset)
        return assets

    def list_for_document(
        self,
        document_id: UUID,
        *,
        asset_type: str | None = None,
        newest_first: bool = True,
        limit: int | None = None,
    ) -> list[GeneratedAsset]:
        statement = select(GeneratedAsset).where(
            GeneratedAsset.document_id == document_id
        )
        if asset_type:
            statement = statement.where(GeneratedAsset.asset_type == asset_type)
        ordering = (
            GeneratedAsset.created_at.desc()
            if newest_first
            else GeneratedAsset.created_at.asc()
        )
        statement = statement.order_by(ordering)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self._session.exec(statement))

    def list_for_pipeline_run(
        self,
        pipeline_run_id: UUID,
        *,
        asset_type: str | None = None,
    ) -> list[GeneratedAsset]:
        statement = select(GeneratedAsset).where(
            GeneratedAsset.pipeline_run_id == pipeline_run_id
        )
        if asset_type:
            statement = statement.where(GeneratedAsset.asset_type == asset_type)
        statement = statement.order_by(GeneratedAsset.created_at.desc())
        return list(self._session.exec(statement))

    def update(
        self,
        asset: GeneratedAsset,
        *,
        data: Mapping[str, object],
        commit: bool = False,
        refresh: bool = True,
    ) -> GeneratedAsset:
        for key, value in data.items():
            if key == "id":
                continue
            if hasattr(asset, key):
                setattr(asset, key, value)
        asset.updated_at = datetime.now(timezone.utc)
        self._session.add(asset)
        self._session.flush()
        if commit:
            self._session.commit()
        if refresh:
            self._session.refresh(asset)
        return asset
