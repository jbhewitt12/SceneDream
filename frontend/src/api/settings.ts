import { OpenAPI } from "@/client"

export type ArtStyle = {
  id: string
  slug: string
  display_name: string
  description: string | null
  is_recommended: boolean
  is_active: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type AppSettings = {
  id: string
  default_scenes_per_run: number
  default_art_style_id: string | null
  created_at: string
  updated_at: string
}

export type AppSettingsBundleResponse = {
  settings: AppSettings
  art_styles: ArtStyle[]
}

export type AppSettingsUpdateRequest = {
  default_scenes_per_run?: number
  default_art_style_id?: string | null
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

export const SettingsApi = {
  async get(): Promise<AppSettingsBundleResponse> {
    const response = await fetch(buildUrl("/api/v1/settings"))
    if (!response.ok) {
      throw new Error(await parseErrorBody(response))
    }
    return (await response.json()) as AppSettingsBundleResponse
  },

  async update(
    payload: AppSettingsUpdateRequest,
  ): Promise<AppSettingsBundleResponse> {
    const response = await fetch(buildUrl("/api/v1/settings"), {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    })
    if (!response.ok) {
      throw new Error(await parseErrorBody(response))
    }
    return (await response.json()) as AppSettingsBundleResponse
  },
}
