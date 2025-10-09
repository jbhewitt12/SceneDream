# Character Tagging Plan

## Context
- Keep the Gemini-powered scene extraction focused on verbatim excerpts so we avoid quality regressions from overloading the initial prompt.
- Introduce a follow-on character tagging pipeline that consumes persisted scenes and enriches them with structured character data without re-querying the EPUB.

## Objectives
- Produce reliable character identities across scenes for downstream ranking, prompt generation, and character profile building.
- Capture visual descriptors, roles, and alias information while maintaining traceability back to the raw excerpt.
- Ensure the workflow remains modular so each stage can evolve independently.

## Pipeline Overview
1. **Scene extraction (existing):** Maintain the current `gemini-2.5-pro` pass that stores raw excerpts, chunk spans, and metadata in `scene_extractions`.
2. **Candidate detection:** Run lightweight NER/regex on the persisted excerpt to seed a list of probable character mentions and known aliases.
3. **LLM tagging:** Use `gemini-2.5-pro` with a dedicated prompt and JSON schema to classify candidates, add descriptors, and suggest canonical hints.
4. **Character resolver:** Embed names/descriptors, match to existing characters, and create or merge records as needed; persist matches and diagnostics.
5. **Asynchronous orchestration:** Trigger the tagging/resolver flow via a worker queue so long scenes do not block scene extraction.

## Stage Details
### Stage 1: Scene Extraction (status quo)
- Preserve the current prompt, chunking, and storage path.
- Record a prompt version string and model parameters in `SceneExtraction.props` for reproducibility.

### Stage 2: Candidate Detection
- Apply spaCy/NER plus hand-tuned regex to list unique proper nouns per scene.
- Carry forward previously known aliases from the character catalog to prime later stages.
- Store the candidate list in a transient payload passed to the tagging stage.

### Stage 3: LLM Tagging
- Prompt `gemini-2.5-pro` with the raw excerpt, candidate list, and known aliases.
- Request JSON objects with fields such as `name`, `canonical_hint`, `aliases`, `visual_descriptors`, `role`, `confidence`, and `character_span` (paragraph/offset indices).
- Persist the raw LLM response in `SceneExtraction.props['character_tagging']` for auditing.

### Stage 4: Character Resolver
- Embed the combination of canonical_hint + descriptors to compare against stored character embeddings.
- Merge into an existing character when similarity passes a configurable threshold; otherwise create a new record.
- Log resolver decisions, confidence scores, and any manual overrides required.
- Update linkage in `scene_characters` and capture mention spans for highlighting in UX.

## Data Model Updates
- `characters`: canonical name, primary_alias, description_summary, visual_traits, first_seen_scene_id, embedding_version/hash, created_at/updated_at.
- `character_aliases`: `character_id`, alias, confidence, source (`llm`, `ner`, `manual`), created_at.
- `scene_characters`: `scene_extraction_id`, `character_id`, role (`primary`, `supporting`, `background`), confidence, mention_span_start/end, resolver_metadata JSON.
- Extend `SceneExtraction.props` with keys for tagging prompt version, tagging output, resolver diagnostics, and source book checksum.

## Operational Safeguards
- Version and store every prompt template (extraction + tagging) so re-runs are traceable.
- Sample regression checks: rerun tagging on select scenes before releasing prompt or resolver updates and diff alias assignments.
- Provide admin tooling to merge/split characters, edit aliases, and mark false positives; log all manual edits.
- Cache embeddings and alias maps centrally to keep resolver output deterministic across runs.
- Add monitors for scenes that fail tagging or resolve to low-confidence matches so they can be re-queued.

## Next Actions
1. Draft the JSON schema and prompt text for the tagging stage; validate against a handful of stored scenes.
2. Implement candidate detection utilities and stage-two job wiring.
3. Ship alembic migrations plus `sqlmodel` definitions for the new tables and relationships.
4. Build the resolver service (embedding lookup, match scoring, persistence) and integrate with a worker queue.
5. Expose lightweight QA tooling or scripts to review character merges/splits before scaling to full-book runs.
