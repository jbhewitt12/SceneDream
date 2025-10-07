from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import ebooklib
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from ebooklib import epub
from sqlmodel import Session

from app.core.db import engine
from app.repositories.scene_extraction import SceneExtractionRepository
from app.services.langchain import gemini_api
from app.services.scene_extraction.scene_refinement import RefinedScene, SceneRefinementError, SceneRefiner


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BOOKS_DIR = PROJECT_ROOT / "books"
EXCESSION_EPUB_PATH = BOOKS_DIR / "Iain Banks" / "Excession" / "Excession - Iain M. Banks.epub"
ENABLE_REFINEMENT = True
REFINEMENT_BATCH_SIZE = 5


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


@dataclass
class SceneExtractionConfig:
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = 0.0
    max_chunk_chars: int = 12000
    chunk_overlap_paragraphs: int = 2
    refinement_model: str = "gemini-2.5-flash"
    refinement_temperature: float = 0.1
    refinement_max_tokens: Optional[int] = None
    book_slug: Optional[str] = None
    enable_refinement: bool = ENABLE_REFINEMENT


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
    paragraph_start: Optional[int] = None
    paragraph_end: Optional[int] = None
    word_start: Optional[int] = None
    word_end: Optional[int] = None

    def signature(self) -> Tuple[str, str]:
        return (self.location_marker.strip().lower(), self.raw_excerpt.strip())


def _batched_scenes(scenes: Sequence[RawScene], batch_size: int) -> Iterable[List[RawScene]]:
    size = max(1, batch_size)
    for start in range(0, len(scenes), size):
        yield list(scenes[start : start + size])



class SceneExtractor:
    def __init__(self, config: Optional[SceneExtractionConfig] = None) -> None:
        self.config = config or SceneExtractionConfig()
        load_dotenv()
        self._refiner: Optional[SceneRefiner] = None

    def extract_book(self, book_path: Union[str, os.PathLike[str]]) -> Dict[str, object]:
        resolved_book_path = self._resolve_book_path(book_path)
        book_slug = self._resolve_book_slug(resolved_book_path)
        chapters = self._load_chapters(resolved_book_path)
        stats = {"book_slug": book_slug, "chapters": len(chapters), "scenes": 0}
        for chapter in chapters:
            print(f"Starting chapter {chapter.number}: {chapter.title}")
            raw_scenes = self._extract_chapter_scenes(chapter, book_slug=book_slug)
            refined_map = self._refine_chapter_scenes(chapter, raw_scenes) if self.config.enable_refinement else {}
            stats["scenes"] += len(raw_scenes)
            self._persist_chapter_scenes(
                book_slug=book_slug,
                book_path=str(resolved_book_path),
                chapter=chapter,
                raw_scenes=raw_scenes,
                refinements=refined_map,
            )
            print(
                f"Finished chapter {chapter.number}: {len(raw_scenes)} new scene(s) saved"
            )
        return stats

    def extract_preview(
        self,
        book_path: Union[str, os.PathLike[str]],
        *,
        max_chapters: int = 1,
        max_chunks_per_chapter: int = 1,
    ) -> Dict[str, object]:
        resolved_book_path = self._resolve_book_path(book_path)
        book_slug = self._resolve_book_slug(resolved_book_path)
        chapters = self._load_chapters(resolved_book_path)
        limit = max(max_chapters, 0)
        selected = chapters[:limit]
        stats = {
            "book_slug": book_slug,
            "chapters": len(selected),
            "scenes": 0,
            "chapters_processed": [],
        }
        if not selected:
            return stats
        chunk_limit = max(max_chunks_per_chapter, 0)
        for chapter in selected:
            print(f"Starting chapter {chapter.number}: {chapter.title}")
            limit_param: Optional[int]
            if chunk_limit == 0:
                limit_param = None
            else:
                limit_param = chunk_limit
            raw_scenes = self._extract_chapter_scenes(
                chapter,
                chunk_limit=limit_param,
                book_slug=book_slug,
            )
            refined_map = self._refine_chapter_scenes(chapter, raw_scenes) if self.config.enable_refinement else {}
            stats["scenes"] += len(raw_scenes)
            total_chunks = len(self._chunk_chapter(chapter))
            chunks_considered = min(total_chunks, chunk_limit) if chunk_limit else total_chunks
            stats["chapters_processed"].append(
                {
                    "chapter_number": chapter.number,
                    "chapter_title": chapter.title,
                    "chunks_considered": chunks_considered,
                    "raw_scenes": len(raw_scenes),
                }
            )
            self._persist_chapter_scenes(
                book_slug=book_slug,
                book_path=book_path,
                chapter=chapter,
                raw_scenes=raw_scenes,
                refinements=refined_map,
            )
            print(
                f"Finished chapter {chapter.number}: {len(raw_scenes)} new scene(s) saved"
            )
        return stats

    def _load_chapters(self, book_path: Path) -> List[Chapter]:
        book = epub.read_epub(str(book_path))
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

    def _extract_chapter_scenes(
        self,
        chapter: Chapter,
        *,
        chunk_limit: Optional[int] = None,
        book_slug: Optional[str] = None,
    ) -> List[RawScene]:
        chunks = self._chunk_chapter(chapter)
        if chunk_limit is not None and chunk_limit <= 0:
            return []
        existing_chunk_indexes = (
            self._existing_processed_chunks(book_slug, chapter)
            if book_slug
            else set()
        )
        raw_candidates: List[RawScene] = []
        processed_chunks = 0
        for chunk in chunks:
            if chunk_limit is not None and processed_chunks >= chunk_limit:
                break
            if chunk.index in existing_chunk_indexes:
                logger.info(
                    "Skipping chapter %s chunk %s; existing outputs detected",
                    chapter.number,
                    chunk.index,
                )
                print(
                    f"  Chunk {chunk.index}: skipped (existing records found)"
                )
                continue
            print(
                f"  Chunk {chunk.index}: extracting paragraphs {chunk.start_paragraph}-{chunk.end_paragraph}"
            )
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
                print(
                    f"  Chunk {chunk.index}: extraction failed ({exc}); continuing"
                )
                continue
            scenes = self._parse_gemini_response(response, chapter, chunk)
            raw_candidates.extend(scenes)
            print(f"  Chunk {chunk.index}: extracted {len(scenes)} scene(s)")
            processed_chunks += 1
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
            "Scan the chapter excerpt and extract EVERY descriptive scene that is visually rich, action-packed, "
            "or atmospheric enough to inspire image or video generation. Focus on moments with concrete, visual details. Never include a scene that lacks concrete, visual details."
        )
        guidelines = (
            "- Use the provided numbered paragraphs to guide location markers.\n"
            "- A scene may span multiple paragraphs; reference them as ranges when needed.\n"
            "- Copy excerpts verbatim from the text without paraphrasing. Copy the entire scene, even if it is a big chunk of text. The purpose is to capture all information from the scenethat can be used to create images or videos.\n"
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
            paragraph_start, paragraph_end = self._parse_location_marker(location)
            parsed.append(
                RawScene(
                    chapter_number=chapter.number,
                    chapter_title=chapter.title,
                    provisional_id=provisional_id,
                    location_marker=location,
                    raw_excerpt=excerpt,
                    chunk_index=chunk.index,
                    chunk_span=(chunk.start_paragraph, chunk.end_paragraph),
                    paragraph_start=paragraph_start,
                    paragraph_end=paragraph_end,
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

    def _existing_processed_chunks(self, book_slug: str, chapter: Chapter) -> set[int]:
        if not book_slug:
            return set()
        with Session(engine) as session:
            repository = SceneExtractionRepository(session)
            return repository.chunk_indexes_for_chapter(
                book_slug=book_slug,
                chapter_number=chapter.number,
            )

    def _get_refiner(self) -> SceneRefiner:
        if not self.config.enable_refinement:
            raise RuntimeError("Refinement is disabled in the current configuration.")
        if self._refiner is None:
            self._refiner = SceneRefiner(
                model=self.config.refinement_model,
                temperature=self.config.refinement_temperature,
                max_tokens=self.config.refinement_max_tokens,
            )
        return self._refiner

    def get_refiner(self) -> SceneRefiner:
        return self._get_refiner()

    def _refine_chapter_scenes(
        self,
        chapter: Chapter,
        scenes: List[RawScene],
    ) -> Dict[int, RefinedScene]:
        if not self.config.enable_refinement:
            return {}
        refiner = self._get_refiner()
        return refiner.refine(chapter, scenes)


    def _persist_chapter_scenes(
        self,
        book_slug: str,
        book_path: Union[str, os.PathLike[str]],
        chapter: Chapter,
        raw_scenes: List[RawScene],
        refinements: Dict[int, RefinedScene],
    ) -> None:
        if not raw_scenes:
            return
        normalized_book_path = str(book_path)
        with Session(engine) as session:
            repository = SceneExtractionRepository(session)
            try:
                for scene in raw_scenes:
                    if scene.scene_id is None:
                        continue
                    refinement = refinements.get(scene.scene_id)
                    raw_text = scene.raw_excerpt.strip()
                    raw_word_count = self._word_count(raw_text)
                    raw_char_count = self._char_count(raw_text)
                    refined_text: Optional[str] = None
                    decision: Optional[str] = None
                    rationale: Optional[str] = None
                    refined_word_count: Optional[int] = None
                    refined_char_count: Optional[int] = None
                    refinement_has_excerpt: Optional[bool] = None
                    if refinement:
                        decision = refinement.decision
                        rationale = refinement.rationale
                        refinement_has_excerpt = False
                    props: dict[str, object] = {}
                    paragraph_start = (
                        scene.paragraph_start
                        if scene.paragraph_start is not None
                        else scene.chunk_span[0]
                    )
                    paragraph_end = (
                        scene.paragraph_end
                        if scene.paragraph_end is not None
                        else scene.chunk_span[1]
                    )
                    now = datetime.now(timezone.utc) if refinement and self.config.enable_refinement else None
                    record = repository.get_by_identity(
                        book_slug=book_slug,
                        chapter_number=scene.chapter_number,
                        scene_number=scene.scene_id,
                    )
                    if record is None:
                        payload = {
                            "book_slug": book_slug,
                            "source_book_path": normalized_book_path,
                            "chapter_number": scene.chapter_number,
                            "chapter_title": scene.chapter_title,
                            "chapter_source_name": chapter.source_name,
                            "scene_number": scene.scene_id,
                            "location_marker": scene.location_marker,
                            "raw": raw_text,
                            "refined": refined_text,
                            "refinement_decision": decision,
                            "refinement_rationale": rationale,
                            "chunk_index": scene.chunk_index,
                            "chunk_paragraph_start": scene.chunk_span[0],
                            "chunk_paragraph_end": scene.chunk_span[1],
                            "raw_word_count": raw_word_count,
                            "raw_char_count": raw_char_count,
                            "refined_word_count": refined_word_count,
                            "refined_char_count": refined_char_count,
                            "raw_signature": self._hash_signature(scene),
                            "extraction_model": self.config.gemini_model,
                            "extraction_temperature": self.config.gemini_temperature,
                            "refinement_model": self.config.refinement_model if self.config.enable_refinement else None,
                            "refinement_temperature": self.config.refinement_temperature if self.config.enable_refinement else None,
                            "refined_at": now,
                            "provisional_id": scene.provisional_id,
                            "location_marker_normalized": scene.location_marker.strip().lower(),
                            "scene_paragraph_start": paragraph_start,
                            "scene_paragraph_end": paragraph_end,
                            "scene_word_start": scene.word_start,
                            "scene_word_end": scene.word_end,
                            "refinement_has_refined_excerpt": refinement_has_excerpt,
                            "props": props,
                        }
                        repository.create(data=payload, commit=False, refresh=False)
                    else:
                        existing_props = dict(record.props or {})
                        for legacy_key in (
                            "provisional_id",
                            "chunk_paragraph_span",
                            "location_marker_normalized",
                            "refinement_summary",
                        ):
                            existing_props.pop(legacy_key, None)
                        existing_props.update(props)
                        update_payload = {
                            "source_book_path": normalized_book_path,
                            "chapter_title": scene.chapter_title,
                            "chapter_source_name": chapter.source_name,
                            "location_marker": scene.location_marker,
                            "raw": raw_text,
                            "chunk_index": scene.chunk_index,
                            "chunk_paragraph_start": scene.chunk_span[0],
                            "chunk_paragraph_end": scene.chunk_span[1],
                            "raw_word_count": raw_word_count,
                            "raw_char_count": raw_char_count,
                            "raw_signature": self._hash_signature(scene),
                            "extraction_model": self.config.gemini_model,
                            "extraction_temperature": self.config.gemini_temperature,
                            "provisional_id": scene.provisional_id,
                            "location_marker_normalized": scene.location_marker.strip().lower(),
                            "scene_paragraph_start": paragraph_start,
                            "scene_paragraph_end": paragraph_end,
                            "scene_word_start": scene.word_start,
                            "scene_word_end": scene.word_end,
                            "refinement_has_refined_excerpt": refinement_has_excerpt,
                            "props": existing_props,
                        }
                        if self.config.enable_refinement:
                            update_payload["refinement_model"] = self.config.refinement_model
                            update_payload["refinement_temperature"] = self.config.refinement_temperature
                        if refinement:
                            update_payload.update(
                                {
                                    "refined": refined_text,
                                    "refinement_decision": decision,
                                    "refinement_rationale": rationale,
                                    "refined_word_count": refined_word_count,
                                    "refined_char_count": refined_char_count,
                                    "refined_at": now,
                                }
                            )
                        repository.update(record, data=update_payload, commit=False, refresh=False)
                session.commit()
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _parse_location_marker(location_marker: str) -> Tuple[Optional[int], Optional[int]]:
        text = location_marker.strip()
        if not text:
            return None, None
        lowered = text.lower()
        paragraph_pattern = re.search(
            r"para(?:graph)?s?\s+(\d+)(?:\s*(?:[-–]|to|through|and|&)\s*(\d+))?",
            lowered,
        )
        if paragraph_pattern:
            start = int(paragraph_pattern.group(1))
            end_raw = paragraph_pattern.group(2)
            end = int(end_raw) if end_raw else start
            return start, end
        if "para" not in lowered:
            return None, None
        numbers = [int(match) for match in re.findall(r"\d+", lowered)]
        if numbers:
            start = numbers[0]
            end = numbers[1] if len(numbers) > 1 else start
            return start, end
        return None, None

    @staticmethod
    def _word_count(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        return len(value.split())

    @staticmethod
    def _char_count(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        return len(value)

    def _hash_signature(self, scene: RawScene) -> str:
        location, excerpt = scene.signature()
        payload = f"{location}::{excerpt}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


    def _resolve_book_slug(self, book_path: Union[str, os.PathLike[str], Path]) -> str:
        if self.config.book_slug:
            return self.config.book_slug
        path = Path(book_path)
        base = path.stem or path.name
        slug = self._slugify(base)
        return slug or "book"

    def _resolve_book_path(self, book_path: Union[str, os.PathLike[str], Path]) -> Path:
        candidate = Path(book_path)
        if candidate.is_absolute() and candidate.exists():
            return candidate

        cwd_candidate = (Path.cwd() / candidate).resolve()
        if cwd_candidate.exists():
            return cwd_candidate

        repo_candidate = (PROJECT_ROOT / candidate).resolve()
        if repo_candidate.exists():
            return repo_candidate

        # Fall back to the absolute variant so downstream callers raise a useful error.
        return cwd_candidate

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scene extraction CLI entry point")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    preview = subparsers.add_parser(
        "preview",
        help="Extract scenes for a limited number of chapters/chunks.",
    )
    preview.add_argument("--book", required=True, help="Path to the EPUB file.")
    preview.add_argument("--chapters", type=int, default=1, help="Maximum chapters to process.")
    preview.add_argument("--chunks", type=int, default=1, help="Maximum chunks per chapter to process.")
    preview.set_defaults(func=_cmd_preview)

    preview_excession = subparsers.add_parser(
        "preview-excession",
        help="Run the first chunk extraction for Excession by Iain M. Banks.",
    )
    preview_excession.set_defaults(
        func=_cmd_preview,
        book=EXCESSION_EPUB_PATH,
        chapters=1,
        chunks=1,
    )
    refine_pending = subparsers.add_parser(
        "refine-pending",
        help="Refine stored scenes that are missing refinement decisions.",
    )
    refine_pending.add_argument("--book", help="Optional book slug filter.")
    refine_pending.add_argument("--chapter", type=int, help="Optional chapter number filter.")
    refine_pending.add_argument("--limit", type=int, help="Maximum number of scenes to consider.")
    refine_pending.add_argument("--model", help="Override the Gemini model used for refinement.")
    refine_pending.add_argument("--temperature", type=float, help="Override the Gemini temperature.")
    refine_pending.add_argument("--max-tokens", type=int, dest="max_tokens", help="Override the max tokens for refinement requests.")
    refine_pending.add_argument(
        "--override",
        action="store_true",
        help="Re-run refinement even for scenes that already have decisions.",
    )
    refine_pending.set_defaults(func=_cmd_refine_pending)

    return parser


def _cmd_preview(args: argparse.Namespace) -> int:
    extractor = SceneExtractor()
    stats = extractor.extract_preview(
        args.book,
        max_chapters=args.chapters,
        max_chunks_per_chapter=args.chunks,
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0

def _cmd_refine_pending(args: argparse.Namespace) -> int:
    config = SceneExtractionConfig(enable_refinement=True)
    if getattr(args, 'model', None):
        config.refinement_model = args.model
    if getattr(args, 'temperature', None) is not None:
        config.refinement_temperature = args.temperature
    if getattr(args, 'max_tokens', None) is not None:
        config.refinement_max_tokens = args.max_tokens
    extractor = SceneExtractor(config=config)
    refiner = extractor.get_refiner()
    limit = args.limit if args.limit and args.limit > 0 else None
    with Session(engine) as session:
        repository = SceneExtractionRepository(session)
        records = repository.list_unrefined(
            book_slug=args.book,
            chapter_number=args.chapter,
            limit=limit,
            include_refined=bool(getattr(args, "override", False)),
        )
        if not records:
            print(
                json.dumps(
                    {
                        "scenes_considered": 0,
                        "scenes_refined": 0,
                        "chapters_processed": 0,
                        "message": "No scenes found for refinement.",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 0
        grouped: dict[tuple[str, int], list] = {}
        for record in records:
            key = (record.book_slug, record.chapter_number)
            grouped.setdefault(key, []).append(record)
        total_refined = 0
        processed_chapters = 0
        chapters_considered = len(grouped)
        for (book_slug, chapter_number), chapter_records in grouped.items():
            print(
                f"Processing {book_slug or 'unknown'} chapter {chapter_number} ("
                f"{len(chapter_records)} pending scene(s))"
            )
            primary = chapter_records[0]
            chapter = Chapter(
                number=chapter_number,
                title=primary.chapter_title,
                paragraphs=[],
                source_name=primary.chapter_source_name
                or primary.chapter_title
                or f"chapter_{chapter_number}",
            )
            raw_scenes: List[RawScene] = []
            for record in chapter_records:
                raw_scenes.append(
                    RawScene(
                        chapter_number=record.chapter_number,
                        chapter_title=record.chapter_title,
                        provisional_id=record.provisional_id or record.scene_number,
                        location_marker=record.location_marker,
                        raw_excerpt=record.raw,
                        chunk_index=record.chunk_index or 0,
                        chunk_span=(
                            record.chunk_paragraph_start or 0,
                            record.chunk_paragraph_end or 0,
                        ),
                        scene_id=record.scene_number,
                        paragraph_start=record.scene_paragraph_start,
                        paragraph_end=record.scene_paragraph_end,
                        word_start=record.scene_word_start,
                        word_end=record.scene_word_end,
                    )
                )
            refinements: Dict[int, RefinedScene] = {}
            batches = list(_batched_scenes(raw_scenes, REFINEMENT_BATCH_SIZE))
            for batch in batches:
                try:
                    batch_refinements = refiner.refine(chapter, batch, fail_on_error=True)
                except SceneRefinementError as exc:
                    session.rollback()
                    raise SystemExit(
                        "Refinement failed for "
                        f"{book_slug} chapter {chapter_number} (batch starting at scene"
                        f" {getattr(batch[0], 'scene_id', '?')}): {exc}"
                    ) from exc
                if not batch_refinements:
                    session.rollback()
                    raise SystemExit(
                        "Refinement returned no decisions for "
                        f"{book_slug} chapter {chapter_number} (batch starting at scene "
                        f"{getattr(batch[0], 'scene_id', '?')})."
                    )
                refinements.update(batch_refinements)
            if raw_scenes and not refinements:
                session.rollback()
                raise SystemExit(
                    f"Refinement returned no decisions for {book_slug} chapter {chapter_number}."
                )
            now = datetime.now(timezone.utc)
            chapter_refined = 0
            for record in chapter_records:
                refinement = refinements.get(record.scene_number)
                if refinement is None:
                    continue
                payload = {
                    "refinement_decision": refinement.decision,
                    "refinement_rationale": refinement.rationale,
                    "refinement_model": config.refinement_model,
                    "refinement_temperature": config.refinement_temperature,
                    "refinement_has_refined_excerpt": False,
                    "refined_at": now,
                }
                repository.update(record, data=payload, commit=False, refresh=False)
                chapter_refined += 1
            if chapter_refined:
                session.commit()
                total_refined += chapter_refined
                processed_chapters += 1
                print(f"  Applied refinement to {chapter_refined} scene(s).")
        if total_refined == 0:
            session.rollback()
        summary = {
            "scenes_considered": len(records),
            "scenes_refined": total_refined,
            "scenes_skipped": len(records) - total_refined,
            "chapters_considered": chapters_considered,
            "chapters_processed": processed_chapters,
        }
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0



def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


__all__ = [
    "SceneExtractor",
    "SceneExtractionConfig",
    "Chapter",
    "ChapterChunk",
    "RawScene",
    "RefinedScene",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
