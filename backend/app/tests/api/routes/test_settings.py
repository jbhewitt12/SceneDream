from uuid import uuid4

from fastapi.testclient import TestClient


def _snapshot_style_lists(client: TestClient) -> dict[str, object]:
    response = client.get("/api/v1/settings/art-style-lists")
    assert response.status_code == 200
    return response.json()


def _restore_style_lists(client: TestClient, snapshot: dict[str, object]) -> None:
    response = client.put(
        "/api/v1/settings/art-style-lists",
        json={
            "recommended_styles": snapshot["recommended_styles"],
            "other_styles": snapshot["other_styles"],
        },
    )
    assert response.status_code == 200


def test_get_settings_returns_defaults(client: TestClient) -> None:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200

    payload = response.json()
    assert "settings" in payload
    assert "art_styles" in payload
    assert payload["settings"]["default_scenes_per_run"] >= 1
    assert len(payload["art_styles"]) > 0


def test_update_settings_persists_values(client: TestClient) -> None:
    initial = client.get("/api/v1/settings")
    assert initial.status_code == 200
    initial_payload = initial.json()

    original_scenes = initial_payload["settings"]["default_scenes_per_run"]
    original_style_id = initial_payload["settings"]["default_art_style_id"]
    art_styles = initial_payload["art_styles"]
    target_style_id = art_styles[0]["id"]

    try:
        response = client.patch(
            "/api/v1/settings",
            json={
                "default_scenes_per_run": 8,
                "default_art_style_id": target_style_id,
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["settings"]["default_scenes_per_run"] == 8
        assert payload["settings"]["default_art_style_id"] == target_style_id
    finally:
        client.patch(
            "/api/v1/settings",
            json={
                "default_scenes_per_run": original_scenes,
                "default_art_style_id": original_style_id,
            },
        )


def test_update_settings_rejects_unknown_art_style(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={"default_art_style_id": str(uuid4())},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Art style not found"


def test_get_art_style_lists_returns_split_lists(client: TestClient) -> None:
    response = client.get("/api/v1/settings/art-style-lists")
    assert response.status_code == 200

    payload = response.json()
    assert "recommended_styles" in payload
    assert "other_styles" in payload
    assert "updated_at" in payload
    assert isinstance(payload["recommended_styles"], list)
    assert isinstance(payload["other_styles"], list)


def test_put_art_style_lists_persists_order_and_updates_settings(
    client: TestClient,
) -> None:
    original_settings_response = client.get("/api/v1/settings")
    assert original_settings_response.status_code == 200
    original_settings = original_settings_response.json()["settings"]
    original_lists = _snapshot_style_lists(client)

    try:
        response = client.put(
            "/api/v1/settings/art-style-lists",
            json={
                "recommended_styles": [
                    "  Alpha Sketch  ",
                    "Beta Vision",
                    "Alpha Sketch",
                    "Shared Palette",
                ],
                "other_styles": [
                    "shared palette",
                    "Gamma Ink",
                    "  ",
                    "Beta Vision",
                    "Delta Etching",
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["recommended_styles"] == [
            "Alpha Sketch",
            "Beta Vision",
            "Shared Palette",
        ]
        assert payload["other_styles"] == ["Gamma Ink", "Delta Etching"]

        lists_response = client.get("/api/v1/settings/art-style-lists")
        assert lists_response.status_code == 200
        assert lists_response.json()["recommended_styles"] == payload["recommended_styles"]
        assert lists_response.json()["other_styles"] == payload["other_styles"]

        settings_response = client.get("/api/v1/settings")
        assert settings_response.status_code == 200
        styles = settings_response.json()["art_styles"]
        active_names = [style["display_name"] for style in styles]
        assert active_names == [
            "Alpha Sketch",
            "Beta Vision",
            "Shared Palette",
            "Gamma Ink",
            "Delta Etching",
        ]
    finally:
        _restore_style_lists(client, original_lists)
        client.patch(
            "/api/v1/settings",
            json={
                "default_scenes_per_run": original_settings["default_scenes_per_run"],
                "default_art_style_id": original_settings["default_art_style_id"],
            },
        )


def test_put_art_style_lists_rejects_empty_payload(client: TestClient) -> None:
    response = client.put(
        "/api/v1/settings/art-style-lists",
        json={
            "recommended_styles": ["  "],
            "other_styles": [],
        },
    )
    assert response.status_code == 422
    assert "At least one art style is required" in response.json()["detail"]
