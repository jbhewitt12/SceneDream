from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import Item, User
from app.tests.utils.user import authentication_token_from_email
from app.tests.utils.utils import get_superuser_token_headers
from models.scene_extraction import SceneExtraction
from models.scene_ranking import SceneRanking
from models.image_prompt import ImagePrompt
from models.generated_image import GeneratedImage


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        init_db(session)
        yield session

        # Clean up test data: delete all test-book entries
        # This acts as a safety net if individual test fixtures fail to clean up

        # Find all test book slugs (both "test-book" and "test-book-{uuid}" patterns)
        statement = select(SceneExtraction.book_slug).distinct()
        all_book_slugs = session.exec(statement).all()
        test_book_slugs = [
            slug for slug in all_book_slugs
            if slug.startswith("test-book") or slug.startswith("gallery-book")
        ]

        # Delete in correct order to respect FK constraints
        for book_slug in test_book_slugs:
            # Get all scenes for this test book
            scenes_stmt = select(SceneExtraction).where(
                SceneExtraction.book_slug == book_slug
            )
            test_scenes = session.exec(scenes_stmt).all()

            for scene in test_scenes:
                # Delete generated images first
                images_stmt = delete(GeneratedImage).where(
                    GeneratedImage.scene_extraction_id == scene.id
                )
                session.execute(images_stmt)

                # Delete image prompts
                prompts_stmt = delete(ImagePrompt).where(
                    ImagePrompt.scene_extraction_id == scene.id
                )
                session.execute(prompts_stmt)

                # Delete scene rankings
                rankings_stmt = delete(SceneRanking).where(
                    SceneRanking.scene_extraction_id == scene.id
                )
                session.execute(rankings_stmt)

                # Delete the scene itself
                session.delete(scene)

        # Clean up original test data
        statement = delete(Item)
        session.execute(statement)
        statement = delete(User)
        session.execute(statement)
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
