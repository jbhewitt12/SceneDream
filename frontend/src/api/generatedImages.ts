import { type CancelablePromise, OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

export type GeneratedImageRead = {
  id: string
  scene_extraction_id: string
  image_prompt_id: string
  book_slug: string
  chapter_number: number
  variant_index: number
  provider: string
  model: string
  size: string
  quality: string
  style: string
  aspect_ratio: string | null
  response_format: string
  storage_path: string
  file_name: string
  width: number | null
  height: number | null
  bytes_approx: number | null
  checksum_sha256: string | null
  request_id: string | null
  error: string | null
  created_at: string
  updated_at: string
}

export type ImagePromptSummary = {
  id: string
  prompt_text: string
  style_tags: string[] | null
  attributes: Record<string, unknown>
}

export type SceneSummary = {
  id: string
  book_slug: string
  chapter_number: number
  chapter_title: string
  scene_number: number
  location_marker: string
  raw: string
  refined: string | null
}

export type GeneratedImageWithContext = {
  image: GeneratedImageRead
  prompt: ImagePromptSummary | null
  scene: SceneSummary | null
}

export type GeneratedImageListResponse = {
  data: GeneratedImageRead[]
  meta: Record<string, unknown>
}

export type ListGeneratedImagesParams = {
  book?: string
  chapter?: number
  sceneId?: string
  promptId?: string
  provider?: string
  model?: string
  newestFirst?: boolean
  limit?: number
  offset?: number
}

export type ListForSceneParams = {
  sceneId: string
  provider?: string
  model?: string
  newestFirst?: boolean
  limit?: number
  offset?: number
  includePrompt?: boolean
  includeScene?: boolean
}

export type GeneratedImageGenerateRequest = {
  book_slug?: string
  chapter_range?: [number, number]
  scene_ids?: string[]
  prompt_ids?: string[]
  limit?: number
  overwrite?: boolean
  quality?: "standard" | "hd"
  preferred_style?: "vivid" | "natural"
  aspect_ratio?: "1:1" | "9:16" | "16:9"
  provider?: string
  model?: string
  response_format?: "b64_json" | "url"
  concurrency?: number
  dry_run?: boolean
}

export type GeneratedImageGenerateResponse = {
  generated_image_ids: string[]
  count: number
  dry_run: boolean
}

export const GeneratedImageApi = {
  list(
    params: ListGeneratedImagesParams = {},
  ): CancelablePromise<GeneratedImageListResponse> {
    return __request<GeneratedImageListResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/generated-images",
      query: {
        book: params.book,
        chapter: params.chapter,
        scene_id: params.sceneId,
        prompt_id: params.promptId,
        provider: params.provider,
        model: params.model,
        newest_first: params.newestFirst ?? true,
        limit: params.limit ?? 24,
        offset: params.offset,
      },
      errors: {
        400: "Bad Request",
        422: "Validation Error",
      },
    })
  },

  retrieve(
    imageId: string,
    includePrompt = true,
    includeScene = true,
  ): CancelablePromise<GeneratedImageWithContext> {
    return __request<GeneratedImageWithContext>(OpenAPI, {
      method: "GET",
      url: "/api/v1/generated-images/{image_id}",
      path: {
        image_id: imageId,
      },
      query: {
        include_prompt: includePrompt,
        include_scene: includeScene,
      },
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },

  listForScene(
    params: ListForSceneParams,
  ): CancelablePromise<GeneratedImageListResponse> {
    return __request<GeneratedImageListResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/generated-images/scene/{scene_id}",
      path: {
        scene_id: params.sceneId,
      },
      query: {
        provider: params.provider,
        model: params.model,
        newest_first: params.newestFirst ?? true,
        limit: params.limit ?? 20,
        offset: params.offset,
        include_prompt: params.includePrompt ?? false,
        include_scene: params.includeScene ?? false,
      },
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },

  generate(
    request: GeneratedImageGenerateRequest,
  ): CancelablePromise<GeneratedImageGenerateResponse> {
    return __request<GeneratedImageGenerateResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/generated-images/generate",
      body: request,
      mediaType: "application/json",
      errors: {
        400: "Bad Request",
        422: "Validation Error",
      },
    })
  },
}
