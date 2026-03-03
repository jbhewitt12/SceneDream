from uuid import uuid4

from fastapi.testclient import TestClient


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
