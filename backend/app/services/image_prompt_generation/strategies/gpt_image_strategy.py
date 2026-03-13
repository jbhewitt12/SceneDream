"""GPT Image prompt generation strategy."""

from __future__ import annotations

from app.core.prompt_art_style import (
    PROMPT_ART_STYLE_MODE_RANDOM_MIX,
    PromptArtStyleMode,
)

from .base import PromptStrategy
from .registry import PromptStrategyRegistry

GPT_IMAGE_CHEATSHEET_PATH = (
    "app/services/image_prompt_generation/cheatsheets/gpt_image_cheatsheet.md"
)


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
            "Transform the excerpt into elite GPT Image prompts that read like detailed concept art direction. "
            "GPT Image 1.5 excels at parsing longer, richly layered prompts - leverage this capacity to create immersive, multi-sensory descriptions. "
            "Structure each prompt in clear layers: lead with a clear central subject and readable scene action, then expand into scene/environment, materials and details, style/medium, and technical direction. "
            "Let each variant amplify the scene's emotional core with concrete sensory cues - specific material textures, ambient motion, symbolic props, weather, and soundscapes - so the moment feels inhabitable. "
            "Use precise photography and visual design language (composition, perspective, palette, lens, lighting) to guide the treatment. "
            "Describe materials with tangible specificity rather than generic quality words - 'weathered brass with verdigris patina' rather than 'detailed metal'. "
            "Include explicit spatial relationships: where elements sit in the frame, how foreground relates to background, what occupies negative space. "
            "GPT Image 1.5 has strong world knowledge - include cultural and temporal markers that inform period-appropriate details automatically. "
            "Scale can be intimate or colossal; choose what the excerpt implies while steering the tone toward wonder, curiosity, or serene tension instead of fear. "
            "If people appear, portray them with agency or calm observation, avoiding language of harm or panic while still honoring the story's stakes."
        )

    def get_cheatsheet_path(self) -> str | None:
        return GPT_IMAGE_CHEATSHEET_PATH

    def get_quality_objectives(
        self, variants_count: int, aspect_ratio_display: str
    ) -> str:
        return (
            "- Aim for 80-150 words per prompt; GPT Image 1.5 handles rich detail exceptionally well.\n"
            "- Embed the chosen medium, art movement, and rendering techniques directly into prompt_text and style_tags, and explain why they fit in attributes.style_intent.\n"
            "- Spotlight unique facets of the scene per variant (alternate subjects, emotional beats, or spatial scales) so the set feels complementary, not redundant.\n"
            f"- Choose aspect ratios from {aspect_ratio_display} to serve the excerpt's intent.\n"
            "- Maintain neutral-to-positive emotional valence, avoiding words that signal harm, panic, or cruelty while still capturing momentum or quiet tension."
        )

    def get_style_strategy(self, mode: PromptArtStyleMode) -> str:
        if mode == PROMPT_ART_STYLE_MODE_RANDOM_MIX:
            return (
                "- Consult the curated Suggested Styles list above and pick unique candidates for each variant.\n"
                "- Explicitly weave the chosen medium or art era into prompt_text and style_tags, describing how it manifests (brush strokes, color blending, line weight, surface treatment).\n"
                "- Bind palette, lighting, and composition decisions to narrative clues so the aesthetic choice feels earned.\n"
                "- Include artist or movement references that reinforce the technique and palette logic (e.g., 'Moebius-inspired line work', 'Miyazaki-esque environmental detail')."
            )

        return (
            "- Use the fixed art style for every variant and describe how it manifests in materials, line work, color blending, or surface treatment.\n"
            "- Vary framing, subject emphasis, lens choice, lighting direction, and spatial relationships so the variants feel complementary without changing style family.\n"
            "- Bind palette, lighting, and composition decisions to narrative clues so the shared style still feels earned.\n"
            "- Include artist or movement references only when they reinforce the same fixed style rather than introducing a new one."
        )

    def get_model_constraints(self) -> str:
        return (
            "GPT Image 1.5 supports significantly longer prompts (~32k characters) and excels at understanding complex, multi-layered descriptions. "
            "Use this capacity to include rich details about lighting sources and their effects on materials, explicit spatial relationships, and tangible texture descriptions. "
            "The style parameter (vivid/natural) is not used by GPT Image - all stylistic direction comes from the prompt itself, so be explicit and detailed about artistic style and medium. "
            "The model has strong world knowledge and can infer period-appropriate details from cultural and temporal cues. "
            "Structure prompts in clear layers for best results: scene/environment → subject/action → materials/details → style/medium → technical direction → constraints. "
            "Use exclusion clauses only when they prevent likely unwanted elements."
        )

    def get_supported_aspect_ratios(self) -> list[str]:
        return ["1:1", "3:2", "2:3"]


# Register the strategy
_gpt_image_strategy = GptImagePromptStrategy()
PromptStrategyRegistry.register(_gpt_image_strategy)

__all__ = ["GptImagePromptStrategy", "GPT_IMAGE_CHEATSHEET_PATH"]
