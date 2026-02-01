"""Output schema builder for image prompt generation."""

from __future__ import annotations

import json


class OutputSchemaBuilder:
    """Build JSON schema definitions for prompt output format."""

    def get_schema_json(self) -> str:
        """Return the JSON schema for prompt variants."""
        schema = {
            "title": "string",
            "prompt_text": "string",
            "style_tags": ["string"],
            "attributes": {
                "camera": "string",
                "lens": "string",
                "composition": "string",
                "lighting": "string",
                "palette": "string",
                "atmosphere": "string",
                "aspect_ratio": "string",
                "style_intent": "string",
                "references": ["string"],
            },
        }
        return json.dumps(schema, indent=2)


__all__ = [
    "OutputSchemaBuilder",
]
