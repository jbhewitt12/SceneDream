from fastapi import APIRouter

from app.api.routes import (
    generated_images,
    image_prompts,
    pipeline_runs,
    scene_extractions,
    scene_rankings,
    settings,
    utils,
)

api_router = APIRouter()
api_router.include_router(utils.router)
api_router.include_router(image_prompts.router)
api_router.include_router(scene_extractions.router)
api_router.include_router(scene_rankings.router)
api_router.include_router(generated_images.router)
api_router.include_router(settings.router)
api_router.include_router(pipeline_runs.router)
