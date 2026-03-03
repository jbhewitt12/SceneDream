"""
Book content parsing service.

This module exposes the shared BookContentService entry point used across the
codebase to load normalized document structure from EPUB, MOBI, TXT, Markdown,
and DOCX sources.

Main entry point:
    BookContentService - loads and caches book content

Data structures:
    BookContent - normalized book representation
    BookChapter - chapter data with normalized paragraphs
    BookMetadata - file metadata and parser version information
"""

from .base import BookChapter, BookContent, BookMetadata
from .book_content_service import BookContentService, BookContentServiceError

__all__ = [
    "BookContent",
    "BookChapter",
    "BookMetadata",
    "BookContentService",
    "BookContentServiceError",
]
