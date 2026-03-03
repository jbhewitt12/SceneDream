from __future__ import annotations

from pathlib import Path

from .base import BookContent, BookMetadata
from .plain_text_utils import (
    build_chapters_from_paragraphs,
    compute_file_checksum,
    extract_declared_title,
    generate_slug,
    split_wrapped_paragraphs,
    trim_project_gutenberg_boilerplate,
)


class TextBookLoader:
    """Load plain text files into the normalized BookContent structure."""

    PARSER_VERSION = "1.0"

    def load(self, path: Path) -> BookContent:
        """Load a TXT file and return BookContent."""
        if not path.exists():
            raise FileNotFoundError(f"TXT document not found: {path}")

        warnings: list[str] = []
        parse_errors: list[str] = []
        checksum = compute_file_checksum(path)

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="replace")
            warnings.append(
                "TXT file contained undecodable UTF-8 bytes; replaced invalid sequences."
            )
            parse_errors.append("utf8_decode_replacement")

        lines = text.splitlines()
        paragraphs = split_wrapped_paragraphs(lines)
        paragraphs, boilerplate_warnings = trim_project_gutenberg_boilerplate(paragraphs)
        warnings.extend(boilerplate_warnings)

        if not paragraphs:
            raise ValueError(f"TXT document '{path}' did not contain readable content.")

        title = extract_declared_title(paragraphs) or path.stem
        chapters = build_chapters_from_paragraphs(
            paragraphs=paragraphs,
            default_title=title,
            source_name_prefix=f"{path.stem}_txt",
        )

        metadata = BookMetadata(
            file_path=path,
            file_checksum=checksum,
            parser_version=self.PARSER_VERSION,
            format="txt",
            warnings=warnings,
            parse_errors=parse_errors,
            source_metadata={
                "line_count": len(lines),
                "paragraph_count": len(paragraphs),
            },
        )

        return BookContent(
            slug=generate_slug(title),
            title=title,
            chapters=chapters,
            metadata=metadata,
            author=None,
        )
