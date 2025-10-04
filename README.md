# SceneDream

## Scene Extraction Pipeline (Step 1)

The `scene_extraction.SceneExtractor` orchestrates Step 1 of the plan: it ingests EPUB chapters, calls Gemini 2.5 Pro to extract visually rich scenes, refines them with xAI Grok, then writes both raw and refined JSON files to `extracted_scenes/<book_slug>/raw` and `extracted_scenes/<book_slug>/refined`.

Usage skeleton (do not run yet):

```python
from scene_extraction import SceneExtractor, SceneExtractionConfig

extractor = SceneExtractor(SceneExtractionConfig())
stats = extractor.extract_book("books/Iain Banks/Excession/Excession - Iain M. Banks.epub")
```

The extractor expects environment variables `GEMINI_API_KEY` and `XAI_API_KEY` to be present (already defined in `.env`). Adjust the config to change chunk sizing, model names, or output directory.
