from fastapi import APIRouter

from app.api.routes import (
    generated_images,
    image_prompts,
    items,
    login,
    private,
    scene_extractions,
    scene_rankings,
    users,
    utils,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(items.router)
api_router.include_router(image_prompts.router)
api_router.include_router(scene_extractions.router)
api_router.include_router(scene_rankings.router)
api_router.include_router(generated_images.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
