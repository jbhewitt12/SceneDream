import { OpenAPI } from "@/client"

export type DocumentDashboardCounts = {
  extracted: number
  ranked: number
  prompts_generated: number
  images_generated: number
}

export type DocumentDashboardStages = {
  extracted: boolean
  ranked: boolean
  prompts_generated: boolean
  images_generated: boolean
}

export type DocumentDashboardRunSummary = {
  id: string
  status: string
  current_stage: string | null
  error_message: string | null
  usage_summary: Record<string, unknown>
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export type DocumentDashboardEntry = {
  document_id: string | null
  slug: string
  display_name: string
  source_path: string
  source_type: string
  file_exists: boolean
  ingestion_state: string | null
  ingestion_error: string | null
  counts: DocumentDashboardCounts
  stages: DocumentDashboardStages
  last_run: DocumentDashboardRunSummary | null
}

export type DocumentDashboardResponse = {
  data: DocumentDashboardEntry[]
  total: number
}

const buildUrl = (path: string) => {
  const base = OpenAPI.BASE ?? ""
  if (base?.endsWith("/")) {
    return `${base.replace(/\/+$/, "")}${path}`
  }
  return `${base}${path}`
}

const parseErrorBody = async (response: Response) => {
  try {
    const payload = await response.json()
    if (payload && typeof payload.detail === "string") {
      return payload.detail
    }
  } catch {
    // fall back to status text below
  }
  return `${response.status} ${response.statusText}`
}

export const DocumentsApi = {
  async getDashboard(): Promise<DocumentDashboardResponse> {
    const response = await fetch(buildUrl("/api/v1/documents/dashboard"))
    if (!response.ok) {
      throw new Error(await parseErrorBody(response))
    }
    return (await response.json()) as DocumentDashboardResponse
  },
}
