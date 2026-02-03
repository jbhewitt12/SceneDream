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
            "GPT Image 1.5 excels at parsing longer, richly layered prompts - leverage this capacity to create immersive, multi-sensory descriptions. "
            "Structure each prompt in clear layers: scene/environment first, then subject/action, followed by materials and details, then style/medium, technical direction (camera, lens, lighting), and finally explicit constraints. "
            "Let each variant amplify the scene's emotional core with concrete sensory cues - specific material textures, ambient motion, symbolic props, weather, and soundscapes - so the moment feels inhabitable. "
            "Use precise photography language (lens focal lengths, lighting terminology, composition rules) to guide the visual treatment. "
            "Describe materials with tangible specificity rather than generic quality words - 'weathered brass with verdigris patina' rather than 'detailed metal'. "
            "Include explicit spatial relationships: where elements sit in the frame, how foreground relates to background, what occupies negative space. "
            "GPT Image 1.5 has strong world knowledge - include cultural and temporal markers that inform period-appropriate details automatically. "
            "Scale can be intimate or colossal; choose what the excerpt implies while steering the tone toward wonder, curiosity, or serene tension instead of fear. "
            "If people appear, portray them with agency or calm observation, avoiding language of harm or panic while still honoring the story's stakes. "
            "End each prompt with explicit constraints stating what must NOT appear (no photorealism, no modern elements, etc.)."
        )

    def get_cheatsheet_path(self) -> str | None:
        return GPT_IMAGE_CHEATSHEET_PATH

    def get_quality_objectives(self, variants_count: int, aspect_ratio_display: str) -> str:
        return (
            "- Aim for 80-150 words per prompt; GPT Image 1.5 handles rich detail exceptionally well.\n"
            "- Embed the chosen medium, art movement, and rendering techniques directly into prompt_text and style_tags, and explain why they fit in attributes.style_intent.\n"
            "- Spotlight unique facets of the scene per variant (alternate subjects, emotional beats, or spatial scales) so the set feels complementary, not redundant.\n"
            f"- Choose aspect ratios from {aspect_ratio_display} to serve the excerpt's intent.\n"
            "- Maintain neutral-to-positive emotional valence, avoiding words that signal harm, panic, or cruelty while still capturing momentum or quiet tension."
        )

    def get_style_strategy(self) -> str:
        return (
            "- Consult the curated Suggested Styles list above and pick unique candidates for each variant.\n"
            "- Explicitly weave the chosen medium or art era into prompt_text and style_tags, describing how it manifests (brush strokes, color blending, line weight, surface treatment).\n"
            "- Bind palette, lighting, and composition decisions to narrative clues so the aesthetic choice feels earned.\n"
            "- Include artist or movement references that reinforce the technique and palette logic (e.g., 'Moebius-inspired line work', 'Miyazaki-esque environmental detail')."
        )

    def get_model_constraints(self) -> str:
        return (
            "GPT Image 1.5 supports significantly longer prompts (~32k characters) and excels at understanding complex, multi-layered descriptions. "
            "Use this capacity to include rich details about lighting sources and their effects on materials, explicit spatial relationships, and tangible texture descriptions. "
            "The style parameter (vivid/natural) is not used by GPT Image - all stylistic direction comes from the prompt itself, so be explicit and detailed about artistic style and medium. "
            "The model has strong world knowledge and can infer period-appropriate details from cultural and temporal cues. "
            "Structure prompts in clear layers for best results: scene/environment → subject/action → materials/details → style/medium → technical direction → constraints. "
            "End prompts with explicit constraints stating what must NOT appear to prevent unwanted elements."
        )

    def get_supported_aspect_ratios(self) -> list[str]:
        return ["1:1", "16:9", "9:16"]


# Register the strategy
_gpt_image_strategy = GptImagePromptStrategy()
PromptStrategyRegistry.register(_gpt_image_strategy)

__all__ = ["GptImagePromptStrategy", "GPT_IMAGE_CHEATSHEET_PATH"]
