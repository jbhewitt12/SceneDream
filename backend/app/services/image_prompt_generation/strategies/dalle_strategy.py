"""DALL-E 3 prompt generation strategy."""

from __future__ import annotations

from .base import PromptStrategy
from .registry import PromptStrategyRegistry

DALLE3_CHEATSHEET_PATH = (
    "app/services/image_prompt_generation/cheatsheets/dalle3_cheatsheet.md"
)


class DallePromptStrategy(PromptStrategy):
    """Prompt generation strategy optimized for DALL-E 3."""

    @property
    def provider_name(self) -> str:
        return "openai"

    def get_system_prompt(self) -> str:
        return (
            "Respond only with strict JSON matching the requested array schema. "
            "Do not include commentary, markdown fences, or trailing text."
        )

    def get_creative_guidance(self) -> str:
        return (
            "Transform the excerpt into elite DALLE3 prompts that read like avant-garde concept art direction without leaning on photorealism. "
            "Let each variant amplify the scene's emotional core with concrete sensory cues - textures, ambient motion, symbolic props, weather, and soundscapes - so the moment feels inhabitable. "
            "Scale can be intimate or colossal; choose what the excerpt implies while steering the tone toward wonder, curiosity, or serene tension instead of fear. "
            "If people appear, portray them with agency or calm observation, avoiding language of harm or panic while still honoring the story's stakes. "
            "Respect cultural and temporal signals and elevate them with imaginative yet coherent embellishments that keep the moment uplifting."
        )

    def get_cheatsheet_path(self) -> str | None:
        return DALLE3_CHEATSHEET_PATH

    def get_quality_objectives(
        self, variants_count: int, aspect_ratio_display: str
    ) -> str:
        return (
            "- Write each prompt like expert art direction, using decisive verbs and tangible nouns over filler language, and keep the text between 28 and 42 words.\n"
            "- Embed the chosen medium, art movement, and rendering techniques directly into the prompt_text and style_tags, and explain why they fit inside attributes.style_intent.\n"
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
            "- Bind palette, lighting, and composition decisions to narrative clues so the aesthetic choice feels earned."
        )

    def get_model_constraints(self) -> str:
        return (
            "DALL-E 3 works best with prompts between 28-42 words that are vivid and specific. "
            "Use the 'vivid' style parameter for dramatic, hyper-real artistic interpretations, "
            "or 'natural' for more realistic, less exaggerated results. "
            "Avoid overly complex or contradictory descriptions."
        )

    def get_supported_aspect_ratios(self) -> list[str]:
        return ["1:1", "7:4", "4:7"]


# Register the strategy
_dalle_strategy = DallePromptStrategy()
PromptStrategyRegistry.register(_dalle_strategy)

__all__ = ["DallePromptStrategy", "DALLE3_CHEATSHEET_PATH"]
