from types import SimpleNamespace

import pytest
from sqlmodel import Session

from app.services.art_style import ArtStyleService


def test_get_sampling_distribution_splits_recommended_and_other(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.repositories.art_style.ArtStyleRepository.list_active",
        lambda self: [
            SimpleNamespace(display_name="Style A", is_recommended=True),
            SimpleNamespace(display_name="Style B", is_recommended=False),
            SimpleNamespace(display_name="Style C", is_recommended=True),
        ],
    )

    service = ArtStyleService(db)
    recommended, other = service.get_sampling_distribution()

    assert recommended == ["Style A", "Style C"]
    assert other == ["Style B"]
