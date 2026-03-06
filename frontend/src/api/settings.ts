import { SettingsService } from "@/client"

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

export const SettingsApi = {
  get(): Promise<AppSettingsBundleResponse> {
    return SettingsService.getSettings()
  },

  update(
    payload: AppSettingsUpdateRequest,
  ): Promise<AppSettingsBundleResponse> {
    return SettingsService.updateSettings({
      requestBody: payload,
    })
  },
}
