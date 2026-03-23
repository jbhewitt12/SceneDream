import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

import sentry_sdk
from app.api.errors import AppHTTPException, app_http_exception_handler
from app.api.main import api_router
from app.core.config import settings
from app.core.db import engine
from app.services.image_generation.batch_scheduler import (
    start_batch_scheduler,
    stop_batch_scheduler,
)
from app.services.pipeline import DocumentStageStatusService
from app.services.social_posting.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


def _sync_document_stage_statuses_on_startup() -> int:
    with Session(engine) as session:
        return DocumentStageStatusService(session).sync_all_documents()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    # Startup
    try:
        synced = await run_in_threadpool(_sync_document_stage_statuses_on_startup)
    except Exception:
        logger.exception("Failed to synchronize document stage statuses on startup")
    else:
        logger.info(
            "Synchronized document stage statuses on startup: synced=%d", synced
        )

    await start_scheduler()
    await start_batch_scheduler()
    yield
    # Shutdown
    await stop_batch_scheduler()
    await stop_scheduler()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)
app.add_exception_handler(AppHTTPException, app_http_exception_handler)  # type: ignore[arg-type]

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount static files for generated images
# Path resolution: backend/app/main.py -> backend -> project root -> img
# In Docker the code lives at /app/app/main.py so parent.parent is the project root.
img_dir = Path(__file__).parent.parent.parent / "img"
if not img_dir.is_dir():
    img_dir = Path(__file__).parent.parent / "img"
if img_dir.exists() and img_dir.is_dir():
    app.mount("/img", StaticFiles(directory=str(img_dir)), name="images")
