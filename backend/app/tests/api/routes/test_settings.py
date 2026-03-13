from typing import cast

from fastapi.testclient import TestClient


def _snapshot_style_lists(client: TestClient) -> dict[str, object]:
    response = client.get("/api/v1/settings/art-style-lists")
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


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
    assert payload["settings"]["default_prompt_art_style_mode"] == "random_mix"
    assert payload["settings"]["default_prompt_art_style_text"] is None
    assert len(payload["art_styles"]) > 0


def test_update_settings_persists_values(client: TestClient) -> None:
    initial = client.get("/api/v1/settings")
    assert initial.status_code == 200
    initial_payload = initial.json()

    original_scenes = initial_payload["settings"]["default_scenes_per_run"]
    original_mode = initial_payload["settings"]["default_prompt_art_style_mode"]
    original_text = initial_payload["settings"]["default_prompt_art_style_text"]

    try:
        response = client.patch(
            "/api/v1/settings",
            json={
                "default_scenes_per_run": 8,
                "default_prompt_art_style_mode": "single_style",
                "default_prompt_art_style_text": "Painterly realism",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["settings"]["default_scenes_per_run"] == 8
        assert payload["settings"]["default_prompt_art_style_mode"] == "single_style"
        assert (
            payload["settings"]["default_prompt_art_style_text"] == "Painterly realism"
        )

        round_trip = client.get("/api/v1/settings")
        assert round_trip.status_code == 200
        round_trip_payload = round_trip.json()
        assert round_trip_payload["settings"]["default_scenes_per_run"] == 8
        assert (
            round_trip_payload["settings"]["default_prompt_art_style_mode"]
            == "single_style"
        )
        assert (
            round_trip_payload["settings"]["default_prompt_art_style_text"]
            == "Painterly realism"
        )
    finally:
        client.patch(
            "/api/v1/settings",
            json={
                "default_scenes_per_run": original_scenes,
                "default_prompt_art_style_mode": original_mode,
                "default_prompt_art_style_text": original_text,
            },
        )


def test_update_settings_accepts_random_mix_and_clears_text(client: TestClient) -> None:
    original = client.get("/api/v1/settings")
    assert original.status_code == 200
    original_settings = original.json()["settings"]

    try:
        response = client.patch(
            "/api/v1/settings",
            json={
                "default_prompt_art_style_mode": "random_mix",
                "default_prompt_art_style_text": "Should be ignored",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["settings"]["default_prompt_art_style_mode"] == "random_mix"
        assert payload["settings"]["default_prompt_art_style_text"] is None

        round_trip = client.get("/api/v1/settings")
        assert round_trip.status_code == 200
        round_trip_payload = round_trip.json()
        assert (
            round_trip_payload["settings"]["default_prompt_art_style_mode"]
            == "random_mix"
        )
        assert round_trip_payload["settings"]["default_prompt_art_style_text"] is None
    finally:
        client.patch(
            "/api/v1/settings",
            json={
                "default_prompt_art_style_mode": original_settings[
                    "default_prompt_art_style_mode"
                ],
                "default_prompt_art_style_text": original_settings[
                    "default_prompt_art_style_text"
                ],
            },
        )


def test_update_settings_rejects_blank_single_style_text(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/settings",
        json={
            "default_prompt_art_style_mode": "single_style",
            "default_prompt_art_style_text": "   ",
        },
    )
    assert response.status_code == 422
    assert (
        "default_prompt_art_style_text is required"
        in response.json()["detail"][0]["msg"]
    )


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
        assert (
            lists_response.json()["recommended_styles"] == payload["recommended_styles"]
        )
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
                "default_prompt_art_style_mode": original_settings[
                    "default_prompt_art_style_mode"
                ],
                "default_prompt_art_style_text": original_settings[
                    "default_prompt_art_style_text"
                ],
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
