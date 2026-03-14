export type DocumentDashboardReadinessFilter = "all" | "ready" | "not_ready"

export type DocumentDashboardSortOrder =
  | "last_updated"
  | "alpha_asc"
  | "alpha_desc"
  | "images_desc"

export type DocumentDashboardPreferences = {
  readinessFilter: DocumentDashboardReadinessFilter
  sourceTypeFilter: string
  sortOrder: DocumentDashboardSortOrder
}

const STORAGE_KEY = "scenedream:document-dashboard-preferences"

const READINESS_FILTERS = new Set<DocumentDashboardReadinessFilter>([
  "all",
  "ready",
  "not_ready",
])

const SORT_ORDERS = new Set<DocumentDashboardSortOrder>([
  "last_updated",
  "alpha_asc",
  "alpha_desc",
  "images_desc",
])

export const DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES: DocumentDashboardPreferences =
  {
    readinessFilter: "all",
    sourceTypeFilter: "",
    sortOrder: "last_updated",
  }

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null

const isReadinessFilter = (
  value: unknown,
): value is DocumentDashboardReadinessFilter =>
  typeof value === "string" &&
  READINESS_FILTERS.has(value as DocumentDashboardReadinessFilter)

const isSortOrder = (value: unknown): value is DocumentDashboardSortOrder =>
  typeof value === "string" &&
  SORT_ORDERS.has(value as DocumentDashboardSortOrder)

export const loadDashboardPreferences = (): DocumentDashboardPreferences => {
  if (typeof window === "undefined") {
    return DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) {
      return DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES
    }

    const parsed = JSON.parse(raw)
    if (!isRecord(parsed)) {
      return DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES
    }

    const readinessFilter = isReadinessFilter(parsed.readinessFilter)
      ? parsed.readinessFilter
      : DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES.readinessFilter
    const sourceTypeFilter =
      typeof parsed.sourceTypeFilter === "string" ? parsed.sourceTypeFilter : ""
    const sortOrder = isSortOrder(parsed.sortOrder)
      ? parsed.sortOrder
      : DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES.sortOrder

    return {
      readinessFilter,
      sourceTypeFilter,
      sortOrder,
    }
  } catch {
    return DEFAULT_DOCUMENT_DASHBOARD_PREFERENCES
  }
}

export const saveDashboardPreferences = (
  preferences: DocumentDashboardPreferences,
): void => {
  if (typeof window === "undefined") {
    return
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
}
