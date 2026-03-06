import { PipelineRunsService } from "@/client"

export type PipelineRunStartRequest = {
  document_id?: string
  book_slug?: string
  book_path?: string
  art_style_id?: string | null
  prompts_per_scene?: number
  ignore_ranking_recommendations?: boolean
  prompts_for_scenes?: number
  images_for_scenes?: number
  skip_extraction?: boolean
  skip_ranking?: boolean
  skip_prompts?: boolean
  quality?: "standard" | "hd"
  style?: "vivid" | "natural" | null
  aspect_ratio?: "1:1" | "9:16" | "16:9" | null
  mode?: "batch" | "sync"
  poll_timeout?: number
  poll_interval?: number
  dry_run?: boolean
}

export type PipelineRun = {
  id: string
  document_id: string | null
  book_slug: string | null
  status: string
  current_stage: string | null
  error_message: string | null
  config_overrides: Record<string, unknown>
  usage_summary: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export const PipelineRunsApi = {
  async start(payload: PipelineRunStartRequest): Promise<PipelineRun> {
    return (await PipelineRunsService.startPipelineRun({
      requestBody: payload,
    })) as PipelineRun
  },

  async get(runId: string): Promise<PipelineRun> {
    return (await PipelineRunsService.getPipelineRun({
      runId,
    })) as PipelineRun
  },
}
