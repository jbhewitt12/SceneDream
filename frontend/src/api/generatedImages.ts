import { type CancelablePromise, OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

export type GeneratedImageRead = {
  id: string
  scene_extraction_id: string
  image_prompt_id: string
  prompt_title?: string | null
  prompt_flavour_text?: string | null
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
  user_approved: boolean | null
  approval_updated_at: string | null
  file_deleted: boolean
  file_deleted_at: string | null
  has_been_posted?: boolean
  is_queued?: boolean
}

export type ImagePromptSummary = {
  id: string
  title?: string | null
  flavour_text?: string | null
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
  approval?: boolean | null
  posted?: boolean
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

export type GeneratedImageRemixRequest = {
  variants_count?: number
  dry_run?: boolean
}

export type GeneratedImageRemixResponse = {
  remix_prompt_ids: string[]
  status: string
  estimated_completion_seconds: number
}

export type GeneratedImageCustomRemixRequest = {
  custom_prompt_text: string
}

export type GeneratedImageCustomRemixResponse = {
  custom_prompt_id: string
  status: string
  estimated_completion_seconds: number
}

export type SocialMediaPostRead = {
  id: string
  generated_image_id: string
  service_name: string
  status: string
  external_id: string | null
  external_url: string | null
  queued_at: string
  posted_at: string | null
  last_attempt_at: string | null
  attempt_count: number
  error_message: string | null
}

export type QueueForPostingResponse = {
  posts: SocialMediaPostRead[]
  message: string
}

export type PostingStatusResponse = {
  posts: SocialMediaPostRead[]
  has_been_posted: boolean
  is_queued: boolean
}

export const GeneratedImageApi = {
  listProviders(): CancelablePromise<string[]> {
    return __request<string[]>(OpenAPI, {
      method: "GET",
      url: "/api/v1/generated-images/providers",
    })
  },

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
        approval: params.approval ?? undefined,
        posted: params.posted,
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

const buildUrl = (path: string) => {
  const base = OpenAPI.BASE ?? ""
  if (base) {
    const sanitizedBase = base.replace(/\/+$/, "")
    return `${sanitizedBase}${path}`
  }
  return path
}

export const updateImageApproval = async (
  imageId: string,
  approved: boolean | null,
) => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/approval`,
  )

  const response = await fetch(url, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ user_approved: approved }),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to update approval: ${message}`)
  }

  return (await response.json()) as GeneratedImageRead
}

export const remixImage = async (
  imageId: string,
  payload: GeneratedImageRemixRequest | undefined = undefined,
): Promise<GeneratedImageRemixResponse> => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/remix`,
  )

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload ?? {}),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to start remix: ${message}`)
  }

  return (await response.json()) as GeneratedImageRemixResponse
}

export const customRemixImage = async (
  imageId: string,
  customPromptText: string,
): Promise<GeneratedImageCustomRemixResponse> => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/custom-remix`,
  )

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ custom_prompt_text: customPromptText }),
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to start custom remix: ${message}`)
  }

  return (await response.json()) as GeneratedImageCustomRemixResponse
}

export const queueForPosting = async (
  imageId: string,
): Promise<QueueForPostingResponse> => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/queue-for-posting`,
  )

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to queue for posting: ${message}`)
  }

  return (await response.json()) as QueueForPostingResponse
}

export const getPostingStatus = async (
  imageId: string,
): Promise<PostingStatusResponse> => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/posting-status`,
  )

  const response = await fetch(url, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
    },
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to get posting status: ${message}`)
  }

  return (await response.json()) as PostingStatusResponse
}

export const cropImage = async (imageId: string, file: Blob): Promise<void> => {
  const url = buildUrl(
    `/api/v1/generated-images/${encodeURIComponent(imageId)}/crop`,
  )

  const formData = new FormData()
  formData.append("file", file)

  const response = await fetch(url, {
    method: "PUT",
    body: formData,
  })

  if (!response.ok) {
    const body = await response.text().catch(() => "")
    const message = body || `${response.status} ${response.statusText}`
    throw new Error(`Failed to crop image: ${message}`)
  }
}
