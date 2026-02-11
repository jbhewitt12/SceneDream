"""Batch image generation service using the OpenAI Batch API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

from openai import OpenAI
from sqlmodel import Session

from app.core.config import settings
from app.repositories.generated_image import GeneratedImageRepository
from app.repositories.image_generation_batch import ImageGenerationBatchRepository
from app.repositories.image_prompt import ImagePromptRepository
from app.repositories.scene_extraction import SceneExtractionRepository
from app.repositories.scene_ranking import SceneRankingRepository
from app.services.image_generation.image_generation_service import (
    GenerationResult,
    GenerationTask,
    ImageGenerationConfig,
    ImageGenerationService,
    compute_file_checksum,
)
from models.image_generation_batch import ImageGenerationBatch

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Quality mapping: DALL-E style values -> GPT Image values
_QUALITY_MAPPING = {"standard": "auto", "hd": "high"}


class BatchImageGenerationService:
    """Generate images via the OpenAI Batch API for 50% cost reduction."""

    def __init__(
        self,
        session: Session,
        config: ImageGenerationConfig | None = None,
        api_key: str | None = None,
        poll_timeout: int = 3600,
        poll_interval: int = 30,
    ) -> None:
        self._session = session
        self._config = config or ImageGenerationConfig()
        self._api_key = (
            api_key
            or self._config.api_key
            or settings.OPENAI_API_KEY
            or os.getenv("OPENAI_API_KEY", "")
        )
        self._poll_timeout = poll_timeout
        self._poll_interval = poll_interval

        # Reuse the sync service for prompt fetching and task building
        self._sync_service = ImageGenerationService(
            session, self._config, self._api_key
        )

        self._image_repo = GeneratedImageRepository(session)
        self._prompt_repo = ImagePromptRepository(session)
        self._scene_repo = SceneExtractionRepository(session)
        self._ranking_repo = SceneRankingRepository(session)
        self._batch_repo = ImageGenerationBatchRepository(session)

        self._client = OpenAI(api_key=self._api_key)

    async def generate_for_selection(
        self,
        *,
        book_slug: str | None = None,
        chapter_range: tuple[int, int] | None = None,
        scene_ids: list[UUID] | None = None,
        prompt_ids: list[UUID] | None = None,
        top_scenes: int | None = None,
        limit: int | None = None,
        quality: str = "standard",
        preferred_style: str | None = None,
        aspect_ratio: str | None = None,
        provider: str = "openai_gpt_image",
        model: str = "gpt-image-1.5",
        response_format: str = "b64_json",
        concurrency: int = 3,
        dry_run: bool = False,
    ) -> list[UUID]:
        """Generate images for a selection of prompts via the Batch API.

        Same signature as ImageGenerationService.generate_for_selection().
        Returns list of generated image IDs (empty in dry-run or if batch
        didn't complete within the poll timeout).
        """
        config = self._config.copy_with(
            provider=provider,
            model=model,
            quality=quality,
            preferred_style=preferred_style,
            aspect_ratio=aspect_ratio,
            response_format=response_format,
            concurrency=concurrency,
            dry_run=dry_run,
        )

        # Reuse the sync service's prompt fetching logic
        prompts = await self._sync_service._fetch_prompts(
            book_slug=book_slug,
            chapter_range=chapter_range,
            scene_ids=scene_ids,
            prompt_ids=prompt_ids,
            top_scenes=top_scenes,
            limit=limit,
        )

        if not prompts:
            logger.info("No prompts found matching the selection criteria")
            return []

        # Reuse the sync service's task building logic
        tasks = self._sync_service._build_tasks(prompts, config)

        if not tasks:
            logger.info("No new tasks to generate (all already exist)")
            return []

        if config.dry_run:
            self._sync_service._log_dry_run(tasks, config)
            return []

        # Build JSONL, submit batch, poll, and process
        jsonl_content = self._build_jsonl(tasks, config)
        batch = self._submit_batch(jsonl_content, tasks, config, book_slug)

        logger.info(
            "Submitted batch %s with %d requests (OpenAI ID: %s)",
            batch.id,
            len(tasks),
            batch.openai_batch_id,
        )

        # Poll with timeout
        batch = await self._poll_batch(batch)

        if batch.status == "completed":
            results = self.process_completed_batch(batch)
            generated_ids = [
                r.generated_image_id
                for r in results
                if r.generated_image_id is not None
            ]
            logger.info(
                "Batch %s completed: %d images generated, %d errors",
                batch.openai_batch_id,
                len(generated_ids),
                sum(1 for r in results if r.error),
            )
            return generated_ids

        if batch.status in ("failed", "expired", "cancelled"):
            logger.error(
                "Batch %s ended with status: %s (error: %s)",
                batch.openai_batch_id,
                batch.status,
                batch.error,
            )
            return []

        # Timeout reached — background scheduler will pick it up
        logger.warning(
            "Batch %s still %s after %ds timeout. "
            "Background scheduler will process results when ready.",
            batch.openai_batch_id,
            batch.status,
            self._poll_timeout,
        )
        return []

    def _build_jsonl(
        self,
        tasks: list[GenerationTask],
        config: ImageGenerationConfig,
    ) -> str:
        """Build .jsonl content for the OpenAI Batch API."""
        lines: list[str] = []

        for task in tasks:
            custom_id = f"{task.prompt.id}_v{task.variant_index}"

            # Apply quality mapping
            mapped_quality = _QUALITY_MAPPING.get(config.quality, config.quality)

            body = {
                "model": config.model,
                "prompt": task.prompt.prompt_text,
                "size": task.size,
                "quality": mapped_quality,
                "output_format": "png",
            }

            line = {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/v1/images/generations",
                "body": body,
            }
            lines.append(json.dumps(line, separators=(",", ":")))

        return "\n".join(lines)

    def _submit_batch(
        self,
        jsonl_content: str,
        tasks: list[GenerationTask],
        config: ImageGenerationConfig,
        book_slug: str | None = None,
    ) -> ImageGenerationBatch:
        """Upload JSONL and create an OpenAI batch job."""
        # Upload input file
        input_file = self._client.files.create(
            file=BytesIO(jsonl_content.encode("utf-8")),
            purpose="batch",
        )

        # Create batch
        openai_batch = self._client.batches.create(
            input_file_id=input_file.id,
            endpoint="/v1/images/generations",
            completion_window="24h",
        )

        # Build task mapping for result processing
        task_mapping = []
        for task in tasks:
            assert task.prompt.scene_extraction is not None
            scene = task.prompt.scene_extraction
            task_mapping.append(
                {
                    "custom_id": f"{task.prompt.id}_v{task.variant_index}",
                    "image_prompt_id": str(task.prompt.id),
                    "scene_extraction_id": str(task.prompt.scene_extraction_id),
                    "variant_index": task.variant_index,
                    "book_slug": scene.book_slug,
                    "chapter_number": scene.chapter_number,
                    "scene_number": scene.scene_number,
                    "storage_path": task.storage_path,
                    "file_name": task.file_name,
                    "aspect_ratio": task.aspect_ratio,
                }
            )

        # Create DB record
        batch_record = self._batch_repo.create(
            data={
                "openai_batch_id": openai_batch.id,
                "openai_input_file_id": input_file.id,
                "status": "submitted",
                "task_mapping": task_mapping,
                "provider": config.provider,
                "model": config.model,
                "quality": config.quality,
                "style": tasks[0].style if tasks else "vivid",
                "size": tasks[0].size if tasks else "1024x1024",
                "total_requests": len(tasks),
                "book_slug": book_slug,
            },
            commit=True,
        )

        return batch_record

    async def _poll_batch(
        self,
        batch: ImageGenerationBatch,
    ) -> ImageGenerationBatch:
        """Poll OpenAI for batch completion with timeout."""
        elapsed = 0

        while elapsed < self._poll_timeout:
            await asyncio.sleep(self._poll_interval)
            elapsed += self._poll_interval

            openai_batch = self._client.batches.retrieve(batch.openai_batch_id)
            new_status = openai_batch.status

            # Update progress counts
            counts = openai_batch.request_counts
            update_kwargs: dict[str, object] = {}
            if counts:
                update_kwargs["completed_requests"] = counts.completed
                update_kwargs["failed_requests"] = counts.failed

            # Handle terminal states
            if new_status == "completed":
                update_kwargs["openai_output_file_id"] = openai_batch.output_file_id
                update_kwargs["openai_error_file_id"] = openai_batch.error_file_id
                update_kwargs["completed_at"] = datetime.now(timezone.utc)
                batch = self._batch_repo.update_status(
                    batch.id, "completed", **update_kwargs
                )  # type: ignore[assignment]
                return batch

            if new_status in ("failed", "expired", "cancelled"):
                errors = []
                if hasattr(openai_batch, "errors") and openai_batch.errors:
                    for err in openai_batch.errors.data:
                        errors.append(f"{err.code}: {err.message}")
                update_kwargs["error"] = "; ".join(errors) if errors else new_status
                update_kwargs["completed_at"] = datetime.now(timezone.utc)
                batch = self._batch_repo.update_status(
                    batch.id, new_status, **update_kwargs
                )  # type: ignore[assignment]
                return batch

            # Still in progress — update status and continue
            if new_status != batch.status:
                batch = self._batch_repo.update_status(
                    batch.id, new_status, **update_kwargs
                )  # type: ignore[assignment]

            logger.info(
                "Batch %s: status=%s, completed=%d/%d, elapsed=%ds",
                batch.openai_batch_id,
                new_status,
                counts.completed if counts else 0,
                batch.total_requests,
                elapsed,
            )

        return batch

    def process_completed_batch(
        self,
        batch: ImageGenerationBatch,
    ) -> list[GenerationResult]:
        """Download results from a completed batch and save images.

        Public so the background scheduler can also call it.
        """
        if not batch.openai_output_file_id:
            logger.error("Batch %s has no output file ID", batch.openai_batch_id)
            return []

        # Build a lookup from custom_id to task mapping
        mapping_lookup: dict[str, dict[str, object]] = {}
        for entry in batch.task_mapping:
            mapping_lookup[str(entry["custom_id"])] = entry

        results: list[GenerationResult] = []

        # Download and process output file
        output_content = self._client.files.content(batch.openai_output_file_id)
        for line in output_content.text.strip().split("\n"):
            if not line.strip():
                continue

            row = json.loads(line)
            custom_id = row["custom_id"]
            mapping = mapping_lookup.get(custom_id)

            if not mapping:
                logger.warning(
                    "No task mapping for custom_id %s in batch %s",
                    custom_id,
                    batch.openai_batch_id,
                )
                continue

            response = row.get("response", {})
            status_code = response.get("status_code", 0)

            if status_code != 200:
                error_body = response.get("body", {}).get("error", {})
                error_msg = error_body.get("message", f"HTTP {status_code}")
                logger.error("Batch request %s failed: %s", custom_id, error_msg)
                results.append(
                    GenerationResult(
                        task=GenerationTask(
                            prompt=None,  # type: ignore[arg-type]
                            variant_index=int(mapping["variant_index"]),
                            size=batch.size,
                            quality=batch.quality,
                            style=batch.style,
                            aspect_ratio=str(mapping["aspect_ratio"])
                            if mapping["aspect_ratio"]
                            else None,
                            storage_path=str(mapping["storage_path"]),
                            file_name=str(mapping["file_name"]),
                        ),
                        error=error_msg,
                    )
                )
                continue

            # Extract base64 image data
            body = response.get("body", {})
            data_list = body.get("data", [])
            if not data_list:
                logger.error("No image data in response for %s", custom_id)
                continue

            b64_data = data_list[0].get("b64_json")
            if not b64_data:
                logger.error("No b64_json in response for %s", custom_id)
                continue

            # Save image to disk
            image_bytes = base64.b64decode(b64_data)
            storage_path = str(mapping["storage_path"])
            file_name = str(mapping["file_name"])
            storage_dir = _PROJECT_ROOT / storage_path
            storage_dir.mkdir(parents=True, exist_ok=True)
            file_path = storage_dir / file_name
            file_path.write_bytes(image_bytes)

            # Compute metadata
            file_size = file_path.stat().st_size
            checksum = compute_file_checksum(file_path)
            width, height = map(int, batch.size.split("x"))

            # Create DB record
            image_data = {
                "scene_extraction_id": mapping["scene_extraction_id"],
                "image_prompt_id": mapping["image_prompt_id"],
                "book_slug": mapping["book_slug"],
                "chapter_number": mapping["chapter_number"],
                "variant_index": mapping["variant_index"],
                "provider": batch.provider,
                "model": batch.model,
                "size": batch.size,
                "quality": batch.quality,
                "style": batch.style,
                "aspect_ratio": mapping["aspect_ratio"],
                "response_format": "b64_json",
                "storage_path": storage_path,
                "file_name": file_name,
                "width": width,
                "height": height,
                "bytes_approx": file_size,
                "checksum_sha256": checksum,
            }

            try:
                generated_image = self._image_repo.create(
                    data=image_data,
                    commit=True,
                )
                results.append(
                    GenerationResult(
                        task=GenerationTask(
                            prompt=None,  # type: ignore[arg-type]
                            variant_index=int(mapping["variant_index"]),
                            size=batch.size,
                            quality=batch.quality,
                            style=batch.style,
                            aspect_ratio=str(mapping["aspect_ratio"])
                            if mapping["aspect_ratio"]
                            else None,
                            storage_path=storage_path,
                            file_name=file_name,
                        ),
                        generated_image_id=generated_image.id,
                    )
                )
                logger.info(
                    "Saved image %s from batch %s (%s/%s)",
                    generated_image.id,
                    batch.openai_batch_id,
                    storage_path,
                    file_name,
                )
            except Exception as exc:
                logger.error("Failed to save image for %s: %s", custom_id, exc)
                results.append(
                    GenerationResult(
                        task=GenerationTask(
                            prompt=None,  # type: ignore[arg-type]
                            variant_index=int(mapping["variant_index"]),
                            size=batch.size,
                            quality=batch.quality,
                            style=batch.style,
                            aspect_ratio=str(mapping["aspect_ratio"])
                            if mapping["aspect_ratio"]
                            else None,
                            storage_path=storage_path,
                            file_name=file_name,
                        ),
                        error=str(exc),
                    )
                )

        # Process error file if present
        if batch.openai_error_file_id:
            try:
                error_content = self._client.files.content(batch.openai_error_file_id)
                for line in error_content.text.strip().split("\n"):
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    logger.error(
                        "Batch error for %s: %s",
                        row.get("custom_id"),
                        row.get("error", {}).get("message", "unknown"),
                    )
            except Exception as exc:
                logger.error("Failed to process error file: %s", exc)

        # Update batch to processed
        completed_count = sum(1 for r in results if r.generated_image_id)
        failed_count = sum(1 for r in results if r.error)
        self._batch_repo.update_status(
            batch.id,
            "processed",
            completed_requests=completed_count,
            failed_requests=failed_count,
        )

        return results
