import {
  type AppSettingsBundleResponse,
  type AppSettingsRead,
  type AppSettingsUpdateRequest,
  type ArtStyleListsRead,
  type ArtStyleListsUpdateRequest,
  type ArtStyleRead,
  SettingsService,
} from "@/client"

export type ArtStyle = ArtStyleRead
export type AppSettings = AppSettingsRead

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

  getArtStyleLists(): Promise<ArtStyleListsRead> {
    return SettingsService.getArtStyleLists()
  },

  updateArtStyleLists(
    payload: ArtStyleListsUpdateRequest,
  ): Promise<ArtStyleListsRead> {
    return SettingsService.updateArtStyleLists({
      requestBody: payload,
    })
  },
}
