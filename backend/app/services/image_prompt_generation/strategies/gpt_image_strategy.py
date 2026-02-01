"""GPT Image prompt generation strategy."""

from __future__ import annotations

from .base import PromptStrategy
from .registry import PromptStrategyRegistry

GPT_IMAGE_CHEATSHEET_PATH = "backend/app/services/image_prompt_generation/cheatsheets/gpt_image_cheatsheet.md"


class GptImagePromptStrategy(PromptStrategy):
    """Prompt generation strategy optimized for GPT Image (gpt-image-1)."""

    @property
    def provider_name(self) -> str:
        return "gpt-image"

    def get_system_prompt(self) -> str:
        return (
            "Respond only with strict JSON matching the requested array schema. "
            "Do not include commentary, markdown fences, or trailing text."
        )

    def get_creative_guidance(self) -> str:
        return (
            "Transform the excerpt into elite GPT Image prompts that read like detailed concept art direction without leaning on photorealism. "
            "GPT Image excels at parsing longer, more detailed prompts - take advantage of this to create rich, layered descriptions. "
            "Let each variant amplify the scene's emotional core with concrete sensory cues - textures, ambient motion, symbolic props, weather, and soundscapes - so the moment feels inhabitable. "
            "Include nuanced details about spatial relationships, lighting sources, and material interactions. "
            "Scale can be intimate or colossal; choose what the excerpt implies while steering the tone toward wonder, curiosity, or serene tension instead of fear. "
            "If people appear, portray them with agency or calm observation, avoiding language of harm or panic while still honoring the story's stakes. "
            "Respect cultural and temporal signals and elevate them with imaginative yet coherent embellishments that keep the moment uplifting."
        )

    def get_cheatsheet_path(self) -> str | None:
        return GPT_IMAGE_CHEATSHEET_PATH

    def get_quality_objectives(self, variants_count: int, aspect_ratio_display: str) -> str:
        return (
            "- Write each prompt like expert art direction, using decisive verbs and tangible nouns over filler language. GPT Image handles longer prompts well, so aim for 40-80 words with rich detail.\n"
            "- Embed the chosen medium, art movement, and rendering techniques directly into the prompt_text and style_tags, and explain why they fit inside attributes.style_intent.\n"
            "- Include secondary details about lighting sources, material textures, and spatial relationships that add depth to the scene.\n"
            "- Spotlight unique facets of the scene per variant (alternate subjects, emotional beats, or spatial scales) so the set feels complementary, not redundant.\n"
            f"- Leverage camera language (shot type, lens, framing) and choose aspect ratios from {aspect_ratio_display} to serve the excerpt's intent.\n"
            "- Maintain neutral-to-positive emotional valence, avoiding words that signal harm, panic, or cruelty while still capturing momentum or quiet tension."
        )

    def get_style_strategy(self) -> str:
        return (
            "- Capture the excerpt's emotional drivers and sensory anchors before drafting prompts.\n"
            "- Consult the curated Suggested Styles list above and pick unique candidates for each variant.\n"
            "- Explicitly weave the chosen medium or art era into prompt_text and style_tags for every variant.\n"
            "- Keep every treatment proudly stylised—never use photorealistic, live-action, or cinematic realism terminology.\n"
            "- Bind palette, lighting, and composition decisions to narrative clues so the aesthetic choice feels earned.\n"
            "- Take advantage of GPT Image's ability to parse complex descriptions - include nuanced details about how style choices manifest in specific elements."
        )

    def get_model_constraints(self) -> str:
        return (
            "GPT Image supports longer prompts (~32k characters) and excels at understanding complex, multi-layered descriptions. "
            "Use this capacity to include rich details about lighting, materials, and spatial relationships. "
            "The style parameter (vivid/natural) is not used by GPT Image - all stylistic direction comes from the prompt itself. "
            "Be explicit about the artistic style and medium in the prompt text."
        )

    def get_supported_aspect_ratios(self) -> list[str]:
        return ["1:1", "16:9", "9:16"]


# Register the strategy
_gpt_image_strategy = GptImagePromptStrategy()
PromptStrategyRegistry.register(_gpt_image_strategy)

__all__ = ["GptImagePromptStrategy", "GPT_IMAGE_CHEATSHEET_PATH"]
