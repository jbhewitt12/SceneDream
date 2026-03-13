import type { PipelineRunStartRequest } from "@/client"

import type { DocumentDashboardEntry } from "@/api/documents"
import {
  type PromptArtStyleSelection,
  getPromptArtStyleTextForPayload,
} from "@/types/promptArtStyle"

const isCompletedStage = (status: string | null | undefined) =>
  status === "completed"

export const shouldLaunchImageGenerationOnly = (
  entry: Pick<DocumentDashboardEntry, "stages">,
) =>
  isCompletedStage(entry.stages.extraction.status) &&
  isCompletedStage(entry.stages.ranking.status)

type BuildPipelineRunStartPayloadParams = {
  entry: DocumentDashboardEntry
  imagesForScenes: number
  promptArtStyleSelection: PromptArtStyleSelection
}

export const buildPipelineRunStartPayload = ({
  entry,
  imagesForScenes,
  promptArtStyleSelection,
}: BuildPipelineRunStartPayloadParams): PipelineRunStartRequest => {
  const payload: PipelineRunStartRequest = {
    document_id: entry.document_id ?? undefined,
    book_slug: entry.document_id ? undefined : entry.slug,
    book_path: entry.document_id ? undefined : entry.source_path,
    images_for_scenes: imagesForScenes,
    prompt_art_style_mode: promptArtStyleSelection.promptArtStyleMode,
    prompt_art_style_text: getPromptArtStyleTextForPayload(
      promptArtStyleSelection,
    ),
  }

  if (shouldLaunchImageGenerationOnly(entry)) {
    payload.skip_extraction = true
    payload.skip_ranking = true
  }

  return payload
}
