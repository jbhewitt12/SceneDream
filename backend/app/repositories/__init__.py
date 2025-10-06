"""Repository layer for database access."""

from .scene_extraction import SceneExtractionRepository
from .scene_ranking import SceneRankingRepository

__all__ = ["SceneExtractionRepository", "SceneRankingRepository"]
