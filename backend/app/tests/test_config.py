from app.core.config import Settings


def test_all_cors_origins_expands_localhost_to_127_alias() -> None:
    settings = Settings(
        PROJECT_NAME="SceneDream",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_DB="app",
        FRONTEND_HOST="http://localhost:5173",
        BACKEND_CORS_ORIGINS=["http://localhost:5173"],
    )

    assert "http://localhost:5173" in settings.all_cors_origins
    assert "http://127.0.0.1:5173" in settings.all_cors_origins


def test_all_cors_origins_expands_127_alias_back_to_localhost() -> None:
    settings = Settings(
        PROJECT_NAME="SceneDream",
        POSTGRES_SERVER="localhost",
        POSTGRES_USER="postgres",
        POSTGRES_DB="app",
        FRONTEND_HOST="http://127.0.0.1:5173",
        BACKEND_CORS_ORIGINS=["http://127.0.0.1:5173"],
    )

    assert "http://127.0.0.1:5173" in settings.all_cors_origins
    assert "http://localhost:5173" in settings.all_cors_origins
