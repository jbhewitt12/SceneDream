import { type CancelablePromise, OpenAPI } from "@/client"
import { request as __request } from "@/client/core/request"

export type SceneRankingSceneSummary = {
  id: string
  book_slug: string
  chapter_number: number
  chapter_title: string
  scene_number: number
  location_marker: string
  refined: string | null
  raw: string
  refinement_decision: string | null
}

export type SceneRanking = {
  id: string
  scene_extraction_id: string
  model_vendor: string
  model_name: string
  prompt_version: string
  justification: string | null
  scores: Record<string, number>
  overall_priority: number
  weight_config: Record<string, number>
  weight_config_hash: string
  warnings: string[] | null
  character_tags: string[] | null
  raw_response: Record<string, unknown>
  execution_time_ms: number | null
  temperature: number | null
  llm_request_id: string | null
  created_at: string
  updated_at: string
  scene: SceneRankingSceneSummary | null
}

export type SceneRankingListResponse = {
  data: SceneRanking[]
  meta: Record<string, unknown>
}

export type SceneRankingTopParams = {
  book_slug?: string
  limit?: number
  model_name?: string | null
  prompt_version?: string | null
  weight_config_hash?: string | null
  include_scene?: boolean
}

export type SceneRankingHistoryParams = {
  limit?: number
  newest_first?: boolean
  include_scene?: boolean
}

const sanitize = (value?: string | null) => {
  if (value === undefined || value === null) {
    return undefined
  }
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : undefined
}

export const SceneRankingService = {
  listTop(
    params: SceneRankingTopParams,
  ): CancelablePromise<SceneRankingListResponse> {
    const { book_slug, include_scene, ...rest } = params
    return __request<SceneRankingListResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-rankings/top",
      query: {
        book_slug,
        include_scene,
        limit: rest.limit,
        model_name: sanitize(rest.model_name),
        prompt_version: sanitize(rest.prompt_version),
        weight_config_hash: sanitize(rest.weight_config_hash),
      },
      errors: {
        422: "Validation Error",
      },
    })
  },

  listSceneHistory(
    sceneId: string,
    params: SceneRankingHistoryParams = {},
  ): CancelablePromise<SceneRankingListResponse> {
    return __request<SceneRankingListResponse>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-rankings/scene/{scene_id}",
      path: {
        scene_id: sceneId,
      },
      query: {
        limit: params.limit,
        newest_first: params.newest_first,
        include_scene: params.include_scene,
      },
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },

  retrieve(
    rankingId: string,
    includeScene?: boolean,
  ): CancelablePromise<SceneRanking> {
    return __request<SceneRanking>(OpenAPI, {
      method: "GET",
      url: "/api/v1/scene-rankings/{ranking_id}",
      path: {
        ranking_id: rankingId,
      },
      query: {
        include_scene: includeScene,
      },
      errors: {
        404: "Not Found",
        422: "Validation Error",
      },
    })
  },
}
