import {
  type AppSettingsBundleResponse,
  type AppSettingsRead,
  type AppSettingsUpdateRequest,
  type ArtStyleListsRead,
  type ArtStyleListsUpdateRequest,
  type ArtStyleRead,
  type ConfigurationTestResponse,
  SettingsService,
} from "@/client"

export type ArtStyle = ArtStyleRead
export type AppSettings = AppSettingsRead
export type SettingsConfigurationTest = ConfigurationTestResponse

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

  resetArtStyleLists(): Promise<ArtStyleListsRead> {
    return SettingsService.resetArtStyleLists()
  },

  testConfiguration(): Promise<ConfigurationTestResponse> {
    return SettingsService.testConfiguration()
  },
}
