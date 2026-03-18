import { type CancelablePromise, OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

type SceneExtractionDateRange = {
  earliest: string | null
  latest: string | null
}

export type SceneExtraction = {
  id: string
  book_slug: string
  source_book_path: string
  chapter_number: number
  chapter_title: string
  chapter_source_name: string | null
  scene_number: number
  location_marker: string
  raw: string
  refined: string | null
  refinement_decision: string | null
  refinement_rationale: string | null
  chunk_index: number
  chunk_paragraph_start: number
  chunk_paragraph_end: number
  raw_word_count: number | null
  raw_char_count: number | null
  refined_word_count: number | null
  refined_char_count: number | null
  raw_signature: string | null
  extraction_model: string | null
  extraction_temperature: number | null
  refinement_model: string | null
  refinement_temperature: number | null
  extracted_at: string
  refined_at: string | null
  props: Record<string, unknown>
}

export type SceneExtractionListResponse = {
  data: SceneExtraction[]
  total: number
  page: number
  page_size: number
}

export type SceneExtractionFilterOptions = {
  books: string[]
  chapters_by_book: Record<string, number[]>
  refinement_decisions: string[]
  has_refined_options: boolean[]
  date_range: SceneExtractionDateRange
}

export type SceneGenerateRequest = {
  num_images: number
  prompt_art_style_mode: string
  prompt_art_style_text: string | null
  quality?: string | null
  aspect_ratio?: string | null
}

export type SceneGenerateResponse = {
  pipeline_run_id: string
  status: string
  message: string
}

export type SceneExtractionListParams = {
  page?: number
  page_size?: number
  book_slug?: string | null
  chapter_number?: number | null
  decision?: string | null
  has_refined?: boolean | null
  search?: string | null
  start_date?: string | null
  end_date?: string | null
  order?: "asc" | "desc"
}

const sanitizeSearchTerm = (term?: string | null) => {
  if (!term) {
    return undefined
  }
  const trimmed = term.trim()
  return trimmed.length > 0 ? trimmed : undefined
}

export const SceneExtractionService = {
  list(
    params: SceneExtractionListParams = {},
  ): CancelablePromise<SceneExtractionListResponse> {
    const query = {
      ...params,
      search: sanitizeSearchTerm(params.search),
    }

    return __request<SceneExtractionListResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-extractions/",
      query,
      errors: {
        422: "Validation Error",
      },
    })
  },

  filters(): CancelablePromise<SceneExtractionFilterOptions> {
    return __request<SceneExtractionFilterOptions>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-extractions/filters",
    })
  },

  retrieve(sceneId: string): CancelablePromise<SceneExtraction> {
    return __request<SceneExtraction>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-extractions/{scene_id}",
      path: {
        scene_id: sceneId,
      },
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },

  generate(
    sceneId: string,
    request: SceneGenerateRequest,
  ): CancelablePromise<SceneGenerateResponse> {
    return __request<SceneGenerateResponse>(OpenAPI, {
      method: "POST",
      url: "/api/v1/scene-extractions/{scene_id}/generate",
      path: {
        scene_id: sceneId,
      },
      body: request,
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },
}
