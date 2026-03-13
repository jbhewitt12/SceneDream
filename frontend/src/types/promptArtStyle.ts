import type { AppSettingsRead } from "@/client"

export type PromptArtStyleMode =
  AppSettingsRead["default_prompt_art_style_mode"]

export type PromptArtStyleSelection = {
  promptArtStyleMode: PromptArtStyleMode
  promptArtStyleText: string
}

type PromptArtStyleSettingsDefaults = Pick<
  AppSettingsRead,
  "default_prompt_art_style_mode" | "default_prompt_art_style_text"
>

export const DEFAULT_PROMPT_ART_STYLE_MODE: PromptArtStyleMode = "random_mix"

export const CUSTOM_ART_STYLE_PLACEHOLDER =
  "e.g. ukiyo-e woodblock, watercolor illustration, gritty graphite sketch"

export const SINGLE_STYLE_REQUIRED_MESSAGE =
  "Custom art style is required when Single art style is selected."

export const getPromptArtStyleSelectionFromSettings = (
  settings: PromptArtStyleSettingsDefaults | null | undefined,
): PromptArtStyleSelection => ({
  promptArtStyleMode:
    settings?.default_prompt_art_style_mode ?? DEFAULT_PROMPT_ART_STYLE_MODE,
  promptArtStyleText: settings?.default_prompt_art_style_text ?? "",
})

export const trimPromptArtStyleText = (value: string) => value.trim()

export const getPromptArtStyleTextForPayload = (
  selection: PromptArtStyleSelection,
) =>
  selection.promptArtStyleMode === "single_style"
    ? trimPromptArtStyleText(selection.promptArtStyleText) || null
    : null

export const getPromptArtStyleValidationMessage = (
  selection: PromptArtStyleSelection,
) =>
  selection.promptArtStyleMode === "single_style" &&
  getPromptArtStyleTextForPayload(selection) === null
    ? SINGLE_STYLE_REQUIRED_MESSAGE
    : null
