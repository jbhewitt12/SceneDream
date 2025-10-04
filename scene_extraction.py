from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import ebooklib
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ebooklib import epub

import gemini_api
from xai_api import XAIAPI


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


SCENE_EXTRACTION_SCHEMA_TEXT = """{
  \"chapter_title\": \"string\",
  \"chapter_number\": \"integer\",
  \"scenes\": [
    {
      \"scene_id\": \"integer\",
      \"location_marker\": \"string\",
      \"raw_excerpt\": \"string\"
    }
  ]
}"""

REFINEMENT_SCHEMA: Dict[str, object] = {
    "type": "object",
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "scene_id": {"type": "integer"},
                    "decision": {"type": "string", "enum": ["keep", "discard"]},
                    "rationale": {"type": "string"},
                    "refined_excerpt": {"type": ["string", "null"]},
                },
                "required": ["scene_id", "decision", "rationale"],
            },
        }
    },
    "required": ["scenes"],
}


@dataclass
class SceneExtractionConfig:
    gemini_model: str = "gemini-2.5-pro-latest"
    gemini_temperature: float = 0.0
    max_chunk_chars: int = 12000
    chunk_overlap_paragraphs: int = 2
    xai_model: str = "grok-beta"
    xai_temperature: float = 0.2
    xai_max_tokens: int = 2048
    output_dir: str = "extracted_scenes"
    book_slug: Optional[str] = None


@dataclass
class Chapter:
    number: int
    title: str
    paragraphs: List[str]
    source_name: str


@dataclass
class ChapterChunk:
    chapter: Chapter
    index: int
    start_paragraph: int
    end_paragraph: int
    paragraphs: Sequence[str]

    def formatted_paragraphs(self) -> str:
        lines: List[str] = []
        for offset, paragraph in enumerate(self.paragraphs):
            paragraph_number = self.start_paragraph + offset
            lines.append(f"[Paragraph {paragraph_number}] {paragraph}")
        return "\n\n".join(lines)


@dataclass
class RawScene:
    chapter_number: int
    chapter_title: str
    provisional_id: int
    location_marker: str
    raw_excerpt: str
    chunk_index: int
    chunk_span: Tuple[int, int]
    scene_id: Optional[int] = None

    def signature(self) -> Tuple[str, str]:
        return (self.location_marker.strip().lower(), self.raw_excerpt.strip())


@dataclass
class RefinedScene:
    scene_id: int
    decision: str
    refined_excerpt: Optional[str]
    rationale: str


class SceneExtractor:
    def __init__(self, config: Optional[SceneExtractionConfig] = None) -> None:
        self.config = config or SceneExtractionConfig()
        load_dotenv()
        self._xai_client: Optional[XAIAPI] = None

    def extract_book(self, book_path: str) -> Dict[str, object]:
        book_slug = self._resolve_book_slug(book_path)
        chapters = self._load_chapters(book_path)
        stats = {"book_slug": book_slug, "chapters": len(chapters), "scenes": 0}
        for chapter in chapters:
            raw_scenes = self._extract_chapter_scenes(chapter)
            refined_map = self._refine_chapter_scenes(chapter, raw_scenes)
            stats["scenes"] += len(raw_scenes)
            self._persist_chapter_scenes(
                book_slug=book_slug,
                book_path=book_path,
                chapter=chapter,
                raw_scenes=raw_scenes,
                refinements=refined_map,
            )
        return stats

    def _load_chapters(self, book_path: str) -> List[Chapter]:
        book = epub.read_epub(book_path)
        chapters: List[Chapter] = []
        chapter_number = 1
        for spine_entry in book.spine:
            item_id = spine_entry[0]
            item = book.get_item_with_id(item_id)
            if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            name = (item.get_name() or "").lower()
            if any(skip in name for skip in ("nav", "cover", "titlepage", "toc")):
                continue
            html = item.get_content().decode("utf-8")
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = self._extract_paragraphs(soup)
            if not paragraphs:
                continue
            title = self._extract_title(soup) or f"Chapter {chapter_number}"
            chapters.append(
                Chapter(
                    number=chapter_number,
                    title=title,
                    paragraphs=paragraphs,
                    source_name=item.get_name() or f"chapter_{chapter_number}",
                )
            )
            chapter_number += 1
        return chapters

    def _extract_paragraphs(self, soup: BeautifulSoup) -> List[str]:
        raw_text = soup.get_text("\n")
        lines = [line.strip() for line in raw_text.splitlines()]
        paragraphs: List[str] = []
        buffer: List[str] = []
        for line in lines:
            if not line:
                if buffer:
                    paragraphs.append(self._normalize_whitespace(" ".join(buffer)))
                    buffer = []
                continue
            buffer.append(line)
        if buffer:
            paragraphs.append(self._normalize_whitespace(" ".join(buffer)))
        cleaned = [p for p in paragraphs if p]
        return cleaned

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in ("h1", "h2", "h3", "title"):
            node = soup.find(selector)
            if node:
                title = node.get_text(strip=True)
                if title:
                    return self._normalize_whitespace(title)
        return None

    def _extract_chapter_scenes(self, chapter: Chapter) -> List[RawScene]:
        chunks = self._chunk_chapter(chapter)
        raw_candidates: List[RawScene] = []
        for chunk in chunks:
            prompt = self._build_chunk_prompt(chunk)
            try:
                response = gemini_api.json_output(
                    prompt=prompt,
                    system_instruction=self._gemini_system_instruction(),
                    model=self.config.gemini_model,
                    temperature=self.config.gemini_temperature,
                )
            except Exception as exc:
                logger.error("Gemini extraction failed for chapter %s chunk %s: %s", chapter.number, chunk.index, exc)
                continue
            scenes = self._parse_gemini_response(response, chapter, chunk)
            raw_candidates.extend(scenes)
        return self._coalesce_scenes(raw_candidates)

    def _chunk_chapter(self, chapter: Chapter) -> List[ChapterChunk]:
        max_chars = max(self.config.max_chunk_chars, 1000)
        overlap = max(self.config.chunk_overlap_paragraphs, 0)
        total = len(chapter.paragraphs)
        chunks: List[ChapterChunk] = []
        pointer = 0
        chunk_index = 0
        while pointer < total:
            char_count = 0
            end = pointer
            while end < total:
                length = len(chapter.paragraphs[end])
                if char_count and char_count + length > max_chars:
                    break
                char_count += length
                end += 1
                if char_count >= max_chars and end > pointer:
                    break
            if end == pointer:
                end = min(pointer + 1, total)
            chunk = ChapterChunk(
                chapter=chapter,
                index=chunk_index,
                start_paragraph=pointer + 1,
                end_paragraph=end,
                paragraphs=chapter.paragraphs[pointer:end],
            )
            chunks.append(chunk)
            if end >= total:
                break
            next_pointer = max(end - overlap, pointer + 1)
            pointer = min(next_pointer, total)
            chunk_index += 1
        return chunks

    def _build_chunk_prompt(self, chunk: ChapterChunk) -> str:
        instructions = (
            "Scan the chapter excerpt and extract every descriptive scene that is visually rich, action-packed, "
            "or atmospheric enough to inspire image or video generation. Focus on moments with concrete, visual details."
        )
        guidelines = (
            "- Use the provided numbered paragraphs to guide location markers.\n"
            "- A scene may span multiple paragraphs; reference them as ranges when needed.\n"
            "- Copy excerpts verbatim from the text without paraphrasing.\n"
            "- If no qualifying scenes exist, return an empty scenes array."
        )
        context_header = (
            f"Book chapter context:\n"
            f"- Chapter number: {chunk.chapter.number}\n"
            f"- Chapter title: {chunk.chapter.title}\n"
            f"- Paragraph span: {chunk.start_paragraph}-{chunk.end_paragraph}\n"
        )
        schema_section = (
            "Output a single JSON object that matches this schema exactly (types shown as comments):\n"
            f"{SCENE_EXTRACTION_SCHEMA_TEXT}\n"
        )
        numbered_paragraphs = chunk.formatted_paragraphs()
        return (
            f"{instructions}\n\n{guidelines}\n\n{schema_section}{context_header}"
            "Numbered chapter excerpt follows. Use it as the only source of truth.\n\n"
            f"{numbered_paragraphs}"
        )

    def _gemini_system_instruction(self) -> str:
        return (
            "You are an expert literary analyst who extracts visually striking scenes from prose. "
            "Respond with valid JSON only and never include commentary or markdown fences."
        )

    def _parse_gemini_response(
        self,
        response: Dict[str, object],
        chapter: Chapter,
        chunk: ChapterChunk,
    ) -> List[RawScene]:
        scenes_data = response.get("scenes") if isinstance(response, dict) else None
        if not isinstance(scenes_data, list):
            logger.warning("Gemini returned unexpected payload for chapter %s chunk %s", chapter.number, chunk.index)
            return []
        parsed: List[RawScene] = []
        for idx, raw_scene in enumerate(scenes_data, start=1):
            if not isinstance(raw_scene, dict):
                continue
            location = str(raw_scene.get("location_marker", "")).strip()
            excerpt = str(raw_scene.get("raw_excerpt", "")).strip()
            if not location or not excerpt:
                continue
            provisional = raw_scene.get("scene_id")
            try:
                provisional_id = int(provisional)
            except (TypeError, ValueError):
                provisional_id = idx
            parsed.append(
                RawScene(
                    chapter_number=chapter.number,
                    chapter_title=chapter.title,
                    provisional_id=provisional_id,
                    location_marker=location,
                    raw_excerpt=excerpt,
                    chunk_index=chunk.index,
                    chunk_span=(chunk.start_paragraph, chunk.end_paragraph),
                )
            )
        return parsed

    def _coalesce_scenes(self, candidates: List[RawScene]) -> List[RawScene]:
        if not candidates:
            return []
        candidates.sort(key=lambda scene: (scene.chunk_index, scene.provisional_id))
        seen: set[Tuple[str, str]] = set()
        unique: List[RawScene] = []
        for scene in candidates:
            signature = scene.signature()
            if signature in seen:
                continue
            seen.add(signature)
            unique.append(scene)
        for index, scene in enumerate(unique, start=1):
            scene.scene_id = index
        return unique

    def _refine_chapter_scenes(
        self,
        chapter: Chapter,
        scenes: List[RawScene],
    ) -> Dict[int, RefinedScene]:
        if not scenes:
            return {}
        prompt = self._build_refinement_prompt(chapter, scenes)
        client = self._get_xai_client()
        try:
            response = client.call_with_json_output(
                prompt=prompt,
                schema=REFINEMENT_SCHEMA,
                system_prompt=self._xai_system_instruction(),
            )
        except Exception as exc:
            logger.error("Refinement failed for chapter %s: %s", chapter.number, exc)
            return {}
        payload = response.model_dump() if hasattr(response, "model_dump") else response
        entries = payload.get("scenes") if isinstance(payload, dict) else None
        refinements: Dict[int, RefinedScene] = {}
        if isinstance(entries, list):
            for item in entries:
                if not isinstance(item, dict):
                    continue
                scene_id = item.get("scene_id")
                if scene_id is None:
                    continue
                try:
                    numeric_id = int(scene_id)
                except (TypeError, ValueError):
                    continue
                decision = item.get("decision", "keep").lower()
                rationale = str(item.get("rationale", "")).strip()
                refined_excerpt = item.get("refined_excerpt")
                if isinstance(refined_excerpt, str):
                    refined_excerpt = refined_excerpt.strip() or None
                refinements[numeric_id] = RefinedScene(
                    scene_id=numeric_id,
                    decision=decision if decision in {"keep", "discard"} else "keep",
                    refined_excerpt=refined_excerpt,
                    rationale=rationale,
                )
        for scene in scenes:
            if scene.scene_id is None:
                continue
            refinements.setdefault(
                scene.scene_id,
                RefinedScene(
                    scene_id=scene.scene_id,
                    decision="keep",
                    refined_excerpt=None,
                    rationale="No refinement returned; retaining original excerpt.",
                ),
            )
        return refinements

    def _build_refinement_prompt(self, chapter: Chapter, scenes: List[RawScene]) -> str:
        header = (
            f"Review the extracted scenes from Chapter {chapter.number} ({chapter.title}).\n"
            "For each scene decide whether it should be kept for image generation.\n"
            "Discard scenes that are primarily dialogue, abstract, or lack concrete visuals.\n"
            "When keeping a scene, enhance the excerpt by emphasizing sensory details already present in the text.\n"
            "Do not invent details; stay faithful to the source.\n"
            "Return structured JSON matching the provided schema."
        )
        scenes_text = []
        for scene in scenes:
            if scene.scene_id is None:
                continue
            scenes_text.append(
                f"Scene {scene.scene_id} | {scene.location_marker}\n" f"{scene.raw_excerpt}\n---"
            )
        scene_body = "\n".join(scenes_text)
        schema_hint = (
            "Schema reminder (types shown as comments):\n"
            "{\n  \"scenes\": [\n    {\n      \"scene_id\": \"integer\",\n      \"decision\": \"keep|discard\",\n      \"rationale\": \"string\",\n      \"refined_excerpt\": \"string or null\"\n    }\n  ]\n}\n"
        )
        return f"{header}\n\n{schema_hint}\nScenes to review:\n\n{scene_body}"

    def _xai_system_instruction(self) -> str:
        return (
            "You evaluate scene extractions for visual storytelling readiness. "
            "Respond with JSON only, following the provided schema exactly."
        )

    def _persist_chapter_scenes(
        self,
        book_slug: str,
        book_path: str,
        chapter: Chapter,
        raw_scenes: List[RawScene],
        refinements: Dict[int, RefinedScene],
    ) -> None:
        if not raw_scenes:
            return
        raw_dir = os.path.join(self.config.output_dir, book_slug, "raw")
        refined_dir = os.path.join(self.config.output_dir, book_slug, "refined")
        os.makedirs(raw_dir, exist_ok=True)
        os.makedirs(refined_dir, exist_ok=True)
        for scene in raw_scenes:
            if scene.scene_id is None:
                continue
            refinement = refinements.get(scene.scene_id)
            slug_source = (refinement.refined_excerpt or scene.raw_excerpt) if refinement else scene.raw_excerpt
            filename = self._scene_filename(scene.chapter_number, scene.scene_id, slug_source)
            raw_payload = {
                "book_slug": book_slug,
                "source_book_path": book_path,
                "chapter_number": scene.chapter_number,
                "chapter_title": scene.chapter_title,
                "scene_id": scene.scene_id,
                "location_marker": scene.location_marker,
                "raw_excerpt": scene.raw_excerpt,
                "chunk_metadata": {
                    "chunk_index": scene.chunk_index,
                    "paragraph_span": list(scene.chunk_span),
                },
            }
            refined_payload = dict(raw_payload)
            if refinement:
                refined_payload["refinement"] = {
                    "decision": refinement.decision,
                    "refined_excerpt": refinement.refined_excerpt,
                    "rationale": refinement.rationale,
                }
            else:
                refined_payload["refinement"] = {
                    "decision": "keep",
                    "refined_excerpt": None,
                    "rationale": "No refinement results available.",
                }
            raw_path = os.path.join(raw_dir, filename)
            refined_path = os.path.join(refined_dir, filename)
            with open(raw_path, "w", encoding="utf-8") as handle:
                json.dump(raw_payload, handle, ensure_ascii=False, indent=2)
            with open(refined_path, "w", encoding="utf-8") as handle:
                json.dump(refined_payload, handle, ensure_ascii=False, indent=2)

    def _get_xai_client(self) -> XAIAPI:
        if self._xai_client is None:
            api_key = os.getenv("XAI_API_KEY")
            if not api_key:
                raise ValueError("XAI_API_KEY is required for scene refinement")
            self._xai_client = XAIAPI(
                api_key=api_key,
                model=self.config.xai_model,
                temperature=self.config.xai_temperature,
                max_tokens=self.config.xai_max_tokens,
            )
        return self._xai_client

    def _resolve_book_slug(self, book_path: str) -> str:
        if self.config.book_slug:
            return self.config.book_slug
        base = os.path.splitext(os.path.basename(book_path))[0]
        slug = self._slugify(base)
        return slug or "book"

    def _scene_filename(self, chapter_number: int, scene_id: int, text: str) -> str:
        slug = self._slugify(text)
        return f"{chapter_number:02d}-{scene_id:03d}-{slug}.json"

    def _slugify(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        tokens = normalized.split()
        if not tokens:
            tokens = ["scene"]
        trimmed = tokens[:6]
        candidate = "-".join(trimmed)
        candidate = re.sub(r"[^a-z0-9-]", "-", candidate)
        candidate = re.sub(r"-+", "-", candidate).strip("-")
        return candidate or "scene"

    def _normalize_whitespace(self, value: str) -> str:
        return " ".join(value.split())


__all__ = [
    "SceneExtractor",
    "SceneExtractionConfig",
    "Chapter",
    "ChapterChunk",
    "RawScene",
    "RefinedScene",
]
