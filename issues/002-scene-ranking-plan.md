# Scene Ranking Plan

## Context
- Step 1 established `SceneExtractor` and persistence in `scene_extractions`, giving us normalized excerpts plus Gemini metadata.
- We now need a repeatable way to evaluate each stored scene for downstream prompt generation, beginning with Gemini `gemini-2.5-flash` but keeping the door open for additional LLMs.

## Objectives
- Score every scene on qualities that influence AI image/video prompt quality and store those scores with justifications.
- Support multiple ranking passes per scene, differentiated by LLM/model, prompt version, and execution metadata.
- Surface the best scenes quickly by consolidating per-criteria scores into an overall recommendation signal.

## Ranking Criteria (1–10 each, numeric + short rationale)
- **originality** – novelty of the setting/action compared to genre tropes.
- **visual_style_potential** – richness of colors, textures, atmosphere that can inform stylistic prompt cues.
- **image_prompt_fit** – how well the core moment compresses into a single still without losing essential meaning.
- **video_prompt_fit** – presence of motion, evolving beats, or multi-step action that would shine in short video.
- **emotional_intensity** – strength/clarity of emotional beats that could drive expression, posing, or lighting choices.
- **worldbuilding_depth** – distinct environmental or lore details that expand creative prompt vocabulary.
- **character_focus** – clarity of key characters, poses, costumes for portrait or group compositions.
- **action_dynamism** – kinetic energy (chases, transformations, battles) that boosts cinematic staging.
- **clarity_for_prompting** – absence of contradictions, overcrowding, or abstract language that might confuse prompt writers or models.
- **overall_priority** – weighted rollup (default heuristic) representing how compelling the scene is for any generative pathway.

Gemini should also return:
- A paragraph justification summarizing high/low scores.
- Recommended prompt angle(s): image vs video vs hybrid suggestions.
- Flags for potential complications (e.g., heavy gore, IP-sensitive content).

## Prompting Strategy with `gemini-2.5-flash`
- System message: outline evaluator role, remind model of 1–10 scale anchors, require JSON.
- User payload: scene text, chapter/paragraph metadata, previously stored model metadata, optional prior rankings for comparison.
- Use `gemini_api.json_output` (temperature ~0.1) with a Pydantic schema capturing the criteria, `overall_priority`, `justification`, `recommendations`, `warnings`, and diagnostic metadata (`model_name`, `prompt_version`).
- Version prompt templates; store version string alongside results so later prompt tweaks are trackable.

## Pipeline Overview
1. **Fetch scenes:** Query `scene_extractions` filtered by chapter/book, optionally skip already-ranked combos.
2. **Compose ranking job:** Bundle scene excerpt, minimal metadata, target model (`gemini-2.5-flash`), and prompt version.
3. **LLM call:** Invoke Gemini, parse JSON, validate score ranges, coerce numeric types.
4. **Persist:** Insert into `scene_rankings` with raw response payload and derived rollups.
5. **Post-processing:** Compute normalized overall scores, maintain leaderboards per book, expose via API/UI.
6. **Re-run support:** Allow reranking with new prompt versions or different models while keeping history.

## Data Model Updates (SQLModel + Alembic)
- New table `scene_rankings`:
  - `id` PK, `scene_extraction_id` FK → `scene_extractions.id` (cascade delete optional).
  - `model_name`, `model_vendor`, `prompt_version` (string).
  - `scores` JSON (keyed by criteria).
  - `overall_priority` (Float), `weight_config` JSON (for future custom weightings).
  - `recommendations` JSON (`prefer_image`, `prefer_video`, rationale).
  - `warnings` JSON or Nullable Text.
  - `raw_response` JSONB for full Gemini output.
  - `execution_time_ms`, `temperature`, `llm_request_id`, timestamps.
  - Unique constraint on (`scene_extraction_id`, `model_name`, `prompt_version`, `weight_config_hash`) to allow multiple models while preventing accidental duplicates.
- Optional linking table later for aggregated leaderboards; not required for first pass.

## Service & API Work
- Create `SceneRankingService` under `backend/app/services/scene_ranking/` handling batching, validation, and persistence.
- Add repository methods for inserting/fetching rankings and for retrieving top scenes per book/chapter.
- Extend FastAPI routes to expose rankings and filter by model/prompt version.
- Provide a CLI entry (`backend/app/services/scene_ranking/main.py`) to rank a slice of scenes (book/chapter filters, dry-run, overwrite options).

## Observability & Safeguards
- Log prompt, response tokens, and failures for auditing; retry transient Gemini errors with exponential backoff.
- Validate score range (1–10) and enforce decimals to one decimal place.
- Diff new rankings against previous ones to spot regressions when prompt versions change.
- Add feature flag to disable ranking for scenes marked discarded during refinement.
- Capture per-run metadata (operator, git SHA) for reproducibility.

## Future-Proofing for Multiple LLMs
- Keep provider/model metadata generic (`model_vendor`, `model_name`).
- Allow storing additional derived metrics (e.g., aggregated consensus) without schema churn via `props` JSON column.
- Design service so the scoring prompt + schema can be swapped based on model capabilities.

## Next Actions
1. Finalize prompt template, schema, and weighting heuristic for Gemini rankings; document prompt version `v1`.
2. Implement `SceneRanking` SqlModel + Alembic migration, repository, and Pydantic response schemas.
3. Build `SceneRankingService` with batching, validation, and CLI harness; wire to `gemini_api.json_output` using `gemini-2.5-flash`.
4. Add API endpoints (list by scene/book, fetch history) and basic tests for repository/service logic.
5. Seed a pilot run on a small chapter, review stored rankings, adjust weights/criteria before scaling book-wide.
