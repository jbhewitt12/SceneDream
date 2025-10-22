import {
  type ImagePromptListResponse,
  type ImagePromptRead,
  ImagePromptsService,
} from "@/client"

export type ImagePromptAttributes = Record<string, unknown>

export type ImagePromptContextWindow = {
  chapterNumber: number | null
  paragraphSpan: [number, number] | null
  paragraphsBefore: number | null
  paragraphsAfter: number | null
  extras?: Record<string, unknown>
}

export type ImagePrompt = Omit<ImagePromptRead, "context_window"> & {
  context_window: ImagePromptContextWindow
}

const toIntegerTuple = (value: unknown): [number, number] | null => {
  if (!Array.isArray(value) || value.length !== 2) {
    return null
  }

  const [start, end] = value
  if (typeof start !== "number" || typeof end !== "number") {
    return null
  }

  return [start, end]
}

const normalizeContextWindow = (
  context: ImagePromptRead["context_window"],
): ImagePromptContextWindow => {
  const chapterNumberRaw = context?.chapter_number
  const paragraphsBeforeRaw = context?.paragraphs_before
  const paragraphsAfterRaw = context?.paragraphs_after

  const chapterNumber =
    typeof chapterNumberRaw === "number" ? chapterNumberRaw : null
  const paragraphsBefore =
    typeof paragraphsBeforeRaw === "number" ? paragraphsBeforeRaw : null
  const paragraphsAfter =
    typeof paragraphsAfterRaw === "number" ? paragraphsAfterRaw : null

  const paragraphSpan = toIntegerTuple(context?.paragraph_span)

  const knownKeys = new Set([
    "chapter_number",
    "paragraph_span",
    "paragraphs_before",
    "paragraphs_after",
  ])

  const extrasEntries = Object.entries(context ?? {}).filter(
    ([key]) => !knownKeys.has(key),
  )

  const extras = extrasEntries.length
    ? Object.fromEntries(extrasEntries)
    : undefined

  return {
    chapterNumber,
    paragraphSpan,
    paragraphsBefore,
    paragraphsAfter,
    extras,
  }
}

const normalizePrompt = (prompt: ImagePromptRead): ImagePrompt => ({
  ...prompt,
  context_window: normalizeContextWindow(prompt.context_window ?? {}),
})

const sanitizeText = (value?: string | null) => {
  if (typeof value !== "string") {
    return undefined
  }
  const trimmed = value.trim()
  return trimmed.length ? trimmed : undefined
}

export type ScenePromptListParams = {
  sceneId: string
  limit?: number
  newestFirst?: boolean
  modelName?: string | null
  promptVersion?: string | null
  includeScene?: boolean
}

export type BookPromptListParams = {
  bookSlug: string
  chapterNumber?: number | null
  modelName?: string | null
  promptVersion?: string | null
  styleTag?: string | null
  newestFirst?: boolean
  page?: number
  pageSize?: number
  includeScene?: boolean
}

export const ImagePromptApi = {
  async listForScene(
    params: ScenePromptListParams,
  ): Promise<ImagePromptListResponse & { data: ImagePrompt[] }> {
    const response = await ImagePromptsService.listPromptsForScene({
      sceneId: params.sceneId,
      limit: params.limit,
      newestFirst: params.newestFirst,
      modelName: sanitizeText(params.modelName),
      promptVersion: sanitizeText(params.promptVersion),
      includeScene: params.includeScene,
    })

    return {
      ...response,
      data: response.data.map(normalizePrompt),
    }
  },

  async listForBook(
    params: BookPromptListParams,
  ): Promise<ImagePromptListResponse & { data: ImagePrompt[] }> {
    const page = params.page && params.page > 0 ? params.page : 1
    const pageSize =
      params.pageSize && params.pageSize > 0 ? params.pageSize : 24
    const offset = (page - 1) * pageSize

    const response = await ImagePromptsService.listPromptsForBook({
      bookSlug: params.bookSlug,
      chapterNumber: params.chapterNumber ?? undefined,
      modelName: sanitizeText(params.modelName),
      promptVersion: sanitizeText(params.promptVersion),
      styleTag: sanitizeText(params.styleTag),
      newestFirst: params.newestFirst === undefined ? true : params.newestFirst,
      limit: pageSize,
      offset,
      includeScene: params.includeScene,
    })

    return {
      ...response,
      data: response.data.map(normalizePrompt),
    }
  },

  async retrieve(promptId: string, includeScene = true): Promise<ImagePrompt> {
    const response = await ImagePromptsService.getImagePrompt({
      promptId,
      includeScene,
    })

    return normalizePrompt(response)
  },
}
