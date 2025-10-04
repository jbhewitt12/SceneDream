# Plan

## Overview

I want to get books written by authors like Ian M. Banks in text format (like epub). Then, I want to use an LLM to extract scenes from the book that would be able to be turned into incredible-looking images or videos. Next, I want to rank the scenes and use an LLM to turn those descriptions into a description that will work well as a prompt for AI image generation. Finally, I want to generate those images or videos.


## Files that already exist

- requirements.txt already exists with these dependencies:
```
langchain==0.3.27
langchain-community==0.3.30
langchain-google-genai==2.1.12
langchain-xai==0.2.5
ebooklib==0.19
```

- .venv already exists and is activated.

- a /Books folder already exists that contains subdirectories that contain the book files. Start with `Books/Iain Banks/Excession/Excession - Iain M. Banks.epub`

- A .env file already exists with the following variables:
```
OPENAI_API_KEY
XAI_API_KEY
GEMINI_API_KEY
```

- gemini_api.py and xai_api.py already exist. Use them to make calls to the LLMs.

## Steps

1. Extract Scenes with LLM

- Ingest the full .epub text. Split it into chapters. For each chapter, load it into the latest Gemini 2.5 pro model (using gemini_api.py) with a prompt like: "Scan the chapter and extract every single descriptive scene that is visually rich, action-packed, or atmospheric—ideal for turning into images/videos. Focus on elements that would be great for images or videos. Output each scene verbatim. Ensure you copy all of the details of the scene. It's fine if it is a big chunk of text because it may be used to create multiple images/videos. Output each scene as a JSON object." The prompt will need to be further refined, and the model should output JSON.

### JSON Schema for Scene Extraction

Instruct the Gemini model to output a single valid JSON object conforming to this schema. No additional text should be included in the response.

```json
{
  "chapter_title": "string",  // The title or identifier of the chapter (e.g., "Chapter 1: The Beginning")
  "chapter_number": "integer",  // The sequential chapter number (starting from 1)
  "scenes": [
    {
      "scene_id": "integer",  // Unique sequential ID for the scene within this chapter (starting from 1)
      "location_marker": "string",  // A marker indicating the location in the chapter (e.g., "Paragraphs 15-22" or "Section 3, sentences 5-12")
      "raw_excerpt": "string"  // The verbatim text excerpt from the book, including all descriptive details
    }
    // Additional scene objects as needed
  ]
}
```

- Chunk long chapters so each Gemini 2.5 Pro call (via gemini_api.py) stays within context limits, and include an explicit JSON schema in the prompt (e.g., keys for chapter, location marker, raw_excerpt). Ask for JSON-only output and capture chapter plus location/paragraph indices instead of page numbers.

- Use a second LLM to refine (e.g., "Critique these extractions: Remove any that are too dialogue-heavy or abstract; enhance descriptions with sensory details from the text"). This iterates to ensure scenes are "image-ready" (vivid, concrete visuals). persist both the raw extraction and the refined version (or a diff note) so changes are auditable and reversible.

- Save scenes under `extracted_scenes/<book_slug>/` using filenames like `{chapter}-{scene_id}-{slug}.json`. Generate collision-safe slugs, and store the same scene_id plus chapter metadata inside each JSON payload to keep filenames aligned with contents.

2. Rank Scenes with LLM

- Use `grok-4-fast-reasoning` to score scenes on criteria like visual potential (e.g., scale of 1-10 for "epicness," "color vibrancy," "dynamic action"), feasibility for AI gen (e.g., avoid overly complex crowds if the tool struggles), and uniqueness.

- LLM-aggressive: Employ a "committee" of LLMs—query the same ranking prompt across 3-5 model instances (or variations) and average scores. To start with, only query Gemini flash as well. Add a feedback loop: "Re-rank based on why lower-scored scenes might improve with better prompting." Top 10-20 scenes proceed.

- Whenever ranking is done, update the file for that scene with standardized JSON that captures all the ranking information. 

3. Convert to Image Prompts with LLM

- For now, let's focus on just creating image prompts, not video prompts. This will make it easier to start with.

- For each ranked scene: LLM prompt `grok-4-fast-reasoning` like: "Transform this scene description into a detailed AI image prompt. Include style (e.g., cinematic, hyper-realistic), lighting, composition, and references to artists like Syd Mead for sci-fi vibes. Optimize for [tool name] to maximize quality."

- LLM-aggressive: Chain refinements—generate initial prompt, then use another LLM to critique ("Does this prompt avoid ambiguities? Suggest improvements for better output fidelity to the book"). Iterate 2-3 times per scene.

- Make an `image_prompts` folder organized into subdirectories by book. Once a prompt is generated and refined save each prompt as a JSON file. For each prompt, we will start the file name with the chapter number, then a dash and then an integer that is the same as the scene it matches and then a short description of the prompt. The integer will be unique and effectively be the ID of the prompt. The JSON should be structured so that there will be many alternates of the prompt potentially in the file.