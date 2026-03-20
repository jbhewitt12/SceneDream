import {
  AlertContent,
  AlertIndicator,
  AlertRoot,
  Badge,
  Box,
  Button,
  Container,
  Flex,
  Grid,
  HStack,
  Heading,
  Input,
  NativeSelectField,
  NativeSelectIndicator,
  NativeSelectRoot,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useMemo, useRef, useState } from "react"
import { FiPlay, FiRefreshCcw, FiSearch } from "react-icons/fi"

import { type DocumentDashboardEntry, DocumentsApi } from "@/api/documents"
import { type PipelineRun, PipelineRunsApi } from "@/api/pipelineRuns"
import { SettingsApi } from "@/api/settings"
import {
  type StageEntry,
  PipelineStageProgress,
} from "@/components/Common/PipelineStageProgress"
import { PromptArtStyleControl } from "@/components/Common/PromptArtStyleControl"
import {
  type DocumentDashboardPreferences,
  loadDashboardPreferences,
  saveDashboardPreferences,
} from "@/features/documents/documentDashboardPreferences"
import {
  buildPipelineRunStartPayload,
  shouldLaunchImageGenerationOnly,
} from "@/features/documents/documentsLaunch"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type PromptArtStyleSelection,
  getPromptArtStyleSelectionFromSettings,
  getPromptArtStyleValidationMessage,
} from "@/types/promptArtStyle"
import { ApiError } from "../../client"

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const body = error.body as Record<string, unknown> | undefined
    if (body && typeof body.detail === "string") return body.detail
  }
  return error instanceof Error ? error.message : fallback
}

export const Route = createFileRoute("/_layout/documents")({
  component: DocumentsPage,
})

const RUN_POLL_INTERVAL_MS = 3000

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "—"
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed)
}

const formatStageStatus = (status: string | null | undefined) => {
  if (!status) {
    return "pending"
  }
  return status.replace(/_/g, " ")
}

const toNumber = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null

const formatUsageSummary = (
  usageSummary: Record<string, unknown> | undefined,
) => {
  if (!usageSummary) {
    return null
  }

  const outputs =
    typeof usageSummary.outputs === "object" && usageSummary.outputs !== null
      ? (usageSummary.outputs as Record<string, unknown>)
      : {}
  const timing =
    typeof usageSummary.timing === "object" && usageSummary.timing !== null
      ? (usageSummary.timing as Record<string, unknown>)
      : {}
  const errors =
    typeof usageSummary.errors === "object" && usageSummary.errors !== null
      ? (usageSummary.errors as Record<string, unknown>)
      : {}

  const promptsGenerated = toNumber(outputs.prompts_generated)
  const imagesGenerated = toNumber(outputs.images_generated)
  const durationMs = toNumber(timing.duration_ms)
  const errorCount = toNumber(errors.count)

  const parts: string[] = []
  if (promptsGenerated !== null) {
    parts.push(`prompts ${promptsGenerated}`)
  }
  if (imagesGenerated !== null) {
    parts.push(`images ${imagesGenerated}`)
  }
  if (durationMs !== null) {
    parts.push(`duration ${(durationMs / 1000).toFixed(1)}s`)
  }
  if (errorCount !== null) {
    parts.push(`errors ${errorCount}`)
  }

  return parts.length ? parts.join(" • ") : null
}

const getUsageSummaryErrorMessages = (
  usageSummary: Record<string, unknown> | undefined,
  primaryError: string | null,
): string[] => {
  if (!usageSummary) return []
  const errors =
    typeof usageSummary.errors === "object" && usageSummary.errors !== null
      ? (usageSummary.errors as Record<string, unknown>)
      : {}
  const messages = Array.isArray(errors.messages) ? errors.messages : []
  const valid = messages.filter(
    (m): m is string => typeof m === "string" && m.length > 0,
  )
  if (!primaryError) return valid
  return valid.filter((m) => m !== primaryError)
}

const statusColor = (status: string | null | undefined) => {
  if (!status) {
    return "gray"
  }
  if (status === "completed") {
    return "green"
  }
  if (status === "failed") {
    return "red"
  }
  if (status === "pending") {
    return "yellow"
  }
  return "blue"
}

const stageStatusColor = (status: string | null | undefined) => {
  if (!status) {
    return "gray"
  }
  if (status === "completed") {
    return "green"
  }
  if (status === "running") {
    return "blue"
  }
  if (status === "failed") {
    return "red"
  }
  if (status === "stale") {
    return "orange"
  }
  return "gray"
}

const isTerminalRunStatus = (status: string | null | undefined) =>
  status === "completed" || status === "failed"

const toEntryKey = (entry: DocumentDashboardEntry) =>
  entry.document_id ?? `${entry.slug}:${entry.source_path}`

const hasOwnKey = (value: object, key: string) =>
  Object.prototype.hasOwnProperty.call(value, key)

const isPipelineReady = (entry: DocumentDashboardEntry) =>
  entry.stages.extraction.status === "completed" &&
  entry.stages.ranking.status === "completed"

const compareDisplayNames = (
  left: DocumentDashboardEntry,
  right: DocumentDashboardEntry,
) =>
  left.display_name.localeCompare(right.display_name, undefined, {
    sensitivity: "base",
  })

const getLastUpdatedTimestamp = (entry: DocumentDashboardEntry) => {
  const value = entry.last_run?.updated_at
  if (!value) {
    return null
  }
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? null : timestamp
}

function DocumentsPage() {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [search, setSearch] = useState("")
  const [preferences, setPreferences] = useState<DocumentDashboardPreferences>(
    loadDashboardPreferences,
  )
  const [scenesPerRunByKey, setScenesPerRunByKey] = useState<
    Record<string, string>
  >({})
  const [artStyleSelectionByKey, setArtStyleSelectionByKey] = useState<
    Record<string, PromptArtStyleSelection>
  >({})
  const [launchingByKey, setLaunchingByKey] = useState<Record<string, boolean>>(
    {},
  )
  const [activeRunByKey, setActiveRunByKey] = useState<
    Record<string, PipelineRun>
  >({})
  const activeRunByKeyRef = useRef(activeRunByKey)

  useEffect(() => {
    activeRunByKeyRef.current = activeRunByKey
  }, [activeRunByKey])

  const updatePreference = (patch: Partial<DocumentDashboardPreferences>) => {
    setPreferences((previous) => {
      const next = { ...previous, ...patch }
      saveDashboardPreferences(next)
      return next
    })
  }

  const dashboardQuery = useQuery({
    queryKey: ["documents", "dashboard"],
    queryFn: () => DocumentsApi.getDashboard(),
    refetchInterval: 10000,
  })

  const settingsQuery = useQuery({
    queryKey: ["settings", "bundle"],
    queryFn: () => SettingsApi.get(),
  })

  const defaultScenesPerRun =
    settingsQuery.data?.settings.default_scenes_per_run ?? 5
  const defaultPromptArtStyleSelection = useMemo(
    () => getPromptArtStyleSelectionFromSettings(settingsQuery.data?.settings),
    [settingsQuery.data?.settings],
  )
  const artStyleCatalogCounts = useMemo(() => {
    const styles = settingsQuery.data?.art_styles ?? []
    return styles.reduce(
      (counts, style) => {
        if (style.is_recommended) {
          counts.recommended += 1
        } else {
          counts.other += 1
        }
        return counts
      },
      { recommended: 0, other: 0 },
    )
  }, [settingsQuery.data?.art_styles])

  const distinctSourceTypes = useMemo(() => {
    const types = new Set(
      (dashboardQuery.data?.data ?? []).map((entry) => entry.source_type),
    )
    return Array.from(types).sort((left, right) => left.localeCompare(right))
  }, [dashboardQuery.data?.data])

  const effectiveSourceTypeFilter = distinctSourceTypes.includes(
    preferences.sourceTypeFilter,
  )
    ? preferences.sourceTypeFilter
    : ""

  useEffect(() => {
    if (
      dashboardQuery.data === undefined ||
      !preferences.sourceTypeFilter ||
      effectiveSourceTypeFilter
    ) {
      return
    }
    setPreferences((previous) => {
      if (!previous.sourceTypeFilter) {
        return previous
      }
      const next = { ...previous, sourceTypeFilter: "" }
      saveDashboardPreferences(next)
      return next
    })
  }, [
    dashboardQuery.data,
    effectiveSourceTypeFilter,
    preferences.sourceTypeFilter,
  ])

  useEffect(() => {
    const hasActiveRuns = Object.values(activeRunByKey).some(
      (run) => !isTerminalRunStatus(run.status),
    )
    if (!hasActiveRuns) {
      return
    }

    let cancelled = false

    const pollRuns = async () => {
      const currentRuns = Object.entries(activeRunByKeyRef.current).filter(
        ([, run]) => !isTerminalRunStatus(run.status),
      )
      if (!currentRuns.length || cancelled) {
        return
      }

      let shouldRefreshDashboard = false

      for (const [key, run] of currentRuns) {
        try {
          const latest = await PipelineRunsApi.get(run.id)
          if (cancelled) {
            return
          }

          setActiveRunByKey((previous) => ({
            ...previous,
            [key]: latest,
          }))

          if (isTerminalRunStatus(latest.status)) {
            shouldRefreshDashboard = true
            if (latest.status === "completed") {
              showSuccessToast("Pipeline run completed.")
            }
            if (latest.status === "failed") {
              showErrorToast(
                latest.error_message ??
                  "Pipeline run failed. Check logs for details.",
              )
            }
          }
        } catch (error) {
          shouldRefreshDashboard = true
          showErrorToast(
            getApiErrorMessage(error, "Failed to poll pipeline run status."),
          )
          setActiveRunByKey((previous) => {
            const next = { ...previous }
            delete next[key]
            return next
          })
        }
      }

      if (shouldRefreshDashboard) {
        void dashboardQuery.refetch()
      }

      if (!cancelled) {
        window.setTimeout(pollRuns, RUN_POLL_INTERVAL_MS)
      }
    }

    const timer = window.setTimeout(pollRuns, RUN_POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [activeRunByKey, dashboardQuery, showErrorToast, showSuccessToast])

  const filteredEntries = useMemo(() => {
    const rows = dashboardQuery.data?.data ?? []
    const term = search.trim().toLowerCase()
    const filtered = rows.filter((row) => {
      const matchesSearch =
        !term ||
        [row.display_name, row.source_path, row.slug].some((value) =>
          value.toLowerCase().includes(term),
        )
      if (!matchesSearch) {
        return false
      }

      if (preferences.readinessFilter === "ready" && !isPipelineReady(row)) {
        return false
      }

      if (preferences.readinessFilter === "not_ready" && isPipelineReady(row)) {
        return false
      }

      if (
        effectiveSourceTypeFilter &&
        row.source_type !== effectiveSourceTypeFilter
      ) {
        return false
      }

      return true
    })

    return [...filtered].sort((left, right) => {
      if (preferences.sortOrder === "alpha_asc") {
        return compareDisplayNames(left, right)
      }

      if (preferences.sortOrder === "alpha_desc") {
        return compareDisplayNames(right, left)
      }

      if (preferences.sortOrder === "images_desc") {
        const byImages =
          right.counts.images_generated - left.counts.images_generated
        return byImages !== 0 ? byImages : compareDisplayNames(left, right)
      }

      const leftTimestamp = getLastUpdatedTimestamp(left)
      const rightTimestamp = getLastUpdatedTimestamp(right)

      if (leftTimestamp === null && rightTimestamp === null) {
        return compareDisplayNames(left, right)
      }
      if (leftTimestamp === null) {
        return 1
      }
      if (rightTimestamp === null) {
        return -1
      }
      if (rightTimestamp !== leftTimestamp) {
        return rightTimestamp - leftTimestamp
      }

      return compareDisplayNames(left, right)
    })
  }, [
    dashboardQuery.data?.data,
    effectiveSourceTypeFilter,
    getLastUpdatedTimestamp,
    preferences.readinessFilter,
    preferences.sortOrder,
    search,
  ])

  const handleLaunch = async (entry: DocumentDashboardEntry) => {
    const key = toEntryKey(entry)
    const hasScenesOverride = hasOwnKey(scenesPerRunByKey, key)
    const hasArtStyleOverride = hasOwnKey(artStyleSelectionByKey, key)
    const scenesRaw = hasScenesOverride
      ? scenesPerRunByKey[key]
      : String(defaultScenesPerRun)
    const imagesForScenes = Number.parseInt(scenesRaw, 10)
    const promptArtStyleSelection = hasArtStyleOverride
      ? artStyleSelectionByKey[key]
      : defaultPromptArtStyleSelection
    const promptArtStyleValidationMessage = getPromptArtStyleValidationMessage(
      promptArtStyleSelection,
    )

    if (!Number.isFinite(imagesForScenes) || imagesForScenes <= 0) {
      showErrorToast("Scenes per run must be a positive integer.")
      return
    }
    if (promptArtStyleValidationMessage) {
      return
    }

    setLaunchingByKey((previous) => ({
      ...previous,
      [key]: true,
    }))

    try {
      const run = await PipelineRunsApi.start(
        buildPipelineRunStartPayload({
          entry,
          imagesForScenes: hasScenesOverride ? imagesForScenes : undefined,
          promptArtStyleSelection: hasArtStyleOverride
            ? promptArtStyleSelection
            : undefined,
        }),
      )

      setActiveRunByKey((previous) => ({
        ...previous,
        [key]: run,
      }))

      showSuccessToast(`Pipeline run started for ${entry.display_name}.`)
      void dashboardQuery.refetch()
    } catch (error) {
      showErrorToast(
        getApiErrorMessage(error, "Failed to launch pipeline run."),
      )
    } finally {
      setLaunchingByKey((previous) => ({
        ...previous,
        [key]: false,
      }))
    }
  }

  return (
    <Container maxW="6xl" py={6}>
      <Stack gap={6}>
        <Flex align="center" justify="space-between" wrap="wrap" gap={3}>
          <Stack gap={1}>
            <Heading size="lg">Documents Dashboard</Heading>
            <Text color="fg.muted">
              Source files and end-to-end pipeline status at a glance.
            </Text>
          </Stack>
          <Button
            variant="outline"
            gap={2}
            onClick={() => dashboardQuery.refetch()}
            loading={dashboardQuery.isFetching}
          >
            <FiRefreshCcw />
            Refresh
          </Button>
        </Flex>

        <Flex gap={3} align={{ base: "stretch", lg: "center" }} wrap="wrap">
          <Box
            position="relative"
            flex="1"
            minW={{ base: "full", md: "320px" }}
          >
            <Box
              position="absolute"
              left={3}
              top="50%"
              transform="translateY(-50%)"
            >
              <FiSearch />
            </Box>
            <Input
              pl={9}
              placeholder="Search by file, path, or slug"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </Box>
          <Flex gap={3} align="center" wrap="wrap">
            <HStack gap={1} borderWidth="1px" borderRadius="md" p={1}>
              <Button
                size="sm"
                variant={
                  preferences.readinessFilter === "all" ? "solid" : "ghost"
                }
                onClick={() => updatePreference({ readinessFilter: "all" })}
              >
                All
              </Button>
              <Button
                size="sm"
                variant={
                  preferences.readinessFilter === "ready" ? "solid" : "ghost"
                }
                onClick={() => updatePreference({ readinessFilter: "ready" })}
              >
                Ready
              </Button>
              <Button
                size="sm"
                variant={
                  preferences.readinessFilter === "not_ready"
                    ? "solid"
                    : "ghost"
                }
                onClick={() =>
                  updatePreference({ readinessFilter: "not_ready" })
                }
              >
                Not Ready
              </Button>
            </HStack>

            <NativeSelectRoot w={{ base: "full", sm: "160px" }}>
              <NativeSelectField
                value={effectiveSourceTypeFilter}
                onChange={(event) =>
                  updatePreference({ sourceTypeFilter: event.target.value })
                }
              >
                <option value="">All types</option>
                {distinctSourceTypes.map((sourceType) => (
                  <option key={sourceType} value={sourceType}>
                    {sourceType.toUpperCase()}
                  </option>
                ))}
              </NativeSelectField>
              <NativeSelectIndicator />
            </NativeSelectRoot>

            <NativeSelectRoot w={{ base: "full", sm: "180px" }}>
              <NativeSelectField
                value={preferences.sortOrder}
                onChange={(event) =>
                  updatePreference({
                    sortOrder: event.target
                      .value as DocumentDashboardPreferences["sortOrder"],
                  })
                }
              >
                <option value="last_updated">Last Updated</option>
                <option value="alpha_asc">Alphabetical (A-Z)</option>
                <option value="alpha_desc">Alphabetical (Z-A)</option>
                <option value="images_desc">Most Images</option>
              </NativeSelectField>
              <NativeSelectIndicator />
            </NativeSelectRoot>

            <Badge colorScheme="blue" px={3} py={1} whiteSpace="nowrap">
              {filteredEntries.length} shown
            </Badge>
          </Flex>
        </Flex>

        {settingsQuery.error ? (
          <AlertRoot status="warning">
            <AlertIndicator />
            <AlertContent>
              {settingsQuery.error instanceof Error
                ? settingsQuery.error.message
                : "Failed to load settings defaults."}
            </AlertContent>
          </AlertRoot>
        ) : null}

        {dashboardQuery.isLoading ? (
          <Flex justify="center" py={12}>
            <Spinner size="lg" />
          </Flex>
        ) : null}

        {dashboardQuery.error ? (
          <AlertRoot status="error">
            <AlertIndicator />
            <AlertContent>
              {dashboardQuery.error instanceof Error
                ? dashboardQuery.error.message
                : "Failed to load document dashboard."}
            </AlertContent>
          </AlertRoot>
        ) : null}

        {!dashboardQuery.isLoading &&
        !dashboardQuery.error &&
        !filteredEntries.length ? (
          <Box borderWidth="1px" borderRadius="lg" p={6}>
            <Text color="fg.muted">
              No documents matched your search and filters, or no files were
              found in `documents/` or `example_docs/`.
            </Text>
          </Box>
        ) : null}

        <Stack gap={4}>
          {filteredEntries.map((entry) => {
            const key = toEntryKey(entry)
            return (
              <DocumentCard
                key={`${entry.source_path}:${entry.slug}`}
                entry={entry}
                activeRun={activeRunByKey[key]}
                scenesPerRunValue={
                  scenesPerRunByKey[key] ?? String(defaultScenesPerRun)
                }
                artStyleSelection={
                  artStyleSelectionByKey[key] ?? defaultPromptArtStyleSelection
                }
                artStyleCatalogCounts={artStyleCatalogCounts}
                launching={launchingByKey[key] === true}
                onScenesPerRunChange={(value) =>
                  setScenesPerRunByKey((previous) => ({
                    ...previous,
                    [key]: value,
                  }))
                }
                onArtStyleModeChange={(promptArtStyleMode) =>
                  setArtStyleSelectionByKey((previous) => ({
                    ...previous,
                    [key]: {
                      ...(previous[key] ?? defaultPromptArtStyleSelection),
                      promptArtStyleMode,
                    },
                  }))
                }
                onArtStyleTextChange={(promptArtStyleText) =>
                  setArtStyleSelectionByKey((previous) => ({
                    ...previous,
                    [key]: {
                      ...(previous[key] ?? defaultPromptArtStyleSelection),
                      promptArtStyleText,
                    },
                  }))
                }
                onLaunch={() => handleLaunch(entry)}
              />
            )
          })}
        </Stack>
      </Stack>
    </Container>
  )
}

type RunSummaryLike = {
  status: string
  current_stage: string | null
  error_message: string | null
  usage_summary?: Record<string, unknown>
  stage_progress?: Record<string, unknown> | null
  completed_at: string | null
}

function DocumentCard({
  entry,
  activeRun,
  scenesPerRunValue,
  artStyleSelection,
  artStyleCatalogCounts,
  launching,
  onScenesPerRunChange,
  onArtStyleModeChange,
  onArtStyleTextChange,
  onLaunch,
}: {
  entry: DocumentDashboardEntry
  activeRun: PipelineRun | undefined
  scenesPerRunValue: string
  artStyleSelection: PromptArtStyleSelection
  artStyleCatalogCounts: {
    recommended: number
    other: number
  }
  launching: boolean
  onScenesPerRunChange: (value: string) => void
  onArtStyleModeChange: (
    value: PromptArtStyleSelection["promptArtStyleMode"],
  ) => void
  onArtStyleTextChange: (value: string) => void
  onLaunch: () => void
}) {
  const runSummary: RunSummaryLike | null =
    activeRun ?? (entry.last_run ? { ...entry.last_run } : null)
  const usageText = runSummary
    ? formatUsageSummary(runSummary.usage_summary)
    : null
  const hasActiveRun =
    activeRun !== undefined && !isTerminalRunStatus(activeRun.status)
  const canGenerateImages = shouldLaunchImageGenerationOnly(entry)
  const launchLabel = canGenerateImages
    ? "Generate images for scenes"
    : "Run pipeline"
  const canLaunch = entry.file_exists || entry.counts.extracted > 0
  const artStyleValidationMessage =
    getPromptArtStyleValidationMessage(artStyleSelection)
  const parsedScenesPerRun = Number.parseInt(scenesPerRunValue, 10)
  const sceneCountSummary = Number.isFinite(parsedScenesPerRun)
    ? `${parsedScenesPerRun} scene${parsedScenesPerRun === 1 ? "" : "s"}`
    : "Select scene count"
  const artStyleSummary =
    artStyleSelection.promptArtStyleMode === "single_style"
      ? artStyleSelection.promptArtStyleText.trim()
        ? `Single art style: ${artStyleSelection.promptArtStyleText.trim()}`
        : "Single art style: enter a custom art style"
      : `Random Style Mix: ${artStyleCatalogCounts.recommended} recommended, ${artStyleCatalogCounts.other} other`
  const launchDescription = canGenerateImages
    ? "Generate images for the highest-ranked scenes that do not already have images."
    : "Run the pipeline for this document with the selected settings."
  const actionHelperText = !canLaunch
    ? "Source file is missing and no extracted scenes exist yet."
    : canGenerateImages
      ? "Only scenes without images will be selected."
      : "Runs extraction, ranking, prompt generation, and image generation as needed."

  return (
    <Box
      p={5}
      borderWidth="1px"
      borderRadius="lg"
      bg="rgba(255,255,255,0.04)"
      backdropFilter="blur(8px) saturate(140%)"
    >
      <Stack gap={4}>
        <Flex justify="space-between" align="center" wrap="wrap" gap={2}>
          <Stack gap={0}>
            <Heading size="md">{entry.display_name}</Heading>
            <Text fontSize="sm" color="fg.muted">
              {entry.source_path}
            </Text>
          </Stack>
          <HStack gap={2}>
            <Badge colorScheme="purple">
              {entry.source_type.toUpperCase()}
            </Badge>
            <Badge colorScheme={entry.file_exists ? "green" : "red"}>
              {entry.file_exists ? "File found" : "File missing"}
            </Badge>
            <Badge colorScheme="gray">{entry.slug}</Badge>
          </HStack>
        </Flex>

        <Grid templateColumns={{ base: "1fr", md: "repeat(4, 1fr)" }} gap={3}>
          <StageBadge
            label="Extracted"
            count={entry.counts.extracted}
            status={entry.stages.extraction.status}
            error={entry.stages.extraction.error}
          />
          <StageBadge
            label="Ranked"
            count={entry.counts.ranked}
            status={entry.stages.ranking.status}
            error={entry.stages.ranking.error}
          />
          <StageBadge
            label="Prompts"
            count={entry.counts.prompts_generated}
            status={entry.stages.prompts_generated.status}
            showStatus={false}
          />
          <StageBadge
            label="Images"
            count={entry.counts.images_generated}
            status={entry.stages.images_generated.status}
            showStatus={false}
          />
        </Grid>

        <Box borderWidth="1px" borderRadius="xl" p={{ base: 4, md: 5 }}>
          <Grid
            templateColumns={{ base: "1fr", xl: "minmax(0, 1fr) 320px" }}
            gap={5}
            alignItems="start"
          >
            <Stack gap={4}>
              <Stack gap={1}>
                <Text fontSize="xs" textTransform="uppercase" color="fg.subtle">
                  Launch Pipeline
                </Text>
                <Text fontSize="sm" color="fg.muted">
                  {launchDescription}
                </Text>
              </Stack>

              <Grid
                templateColumns={{ base: "1fr", lg: "220px minmax(0, 1fr)" }}
                gap={4}
                alignItems="start"
              >
                <Box maxW={{ base: "full", lg: "220px" }}>
                  <Text fontSize="sm" color="fg.muted" mb={1}>
                    Scenes this run
                  </Text>
                  <Input
                    type="number"
                    min={1}
                    value={scenesPerRunValue}
                    onChange={(event) =>
                      onScenesPerRunChange(event.target.value)
                    }
                  />
                </Box>
                <PromptArtStyleControl
                  label="Art style"
                  selection={artStyleSelection}
                  recommendedCount={artStyleCatalogCounts.recommended}
                  otherCount={artStyleCatalogCounts.other}
                  randomMixManageCopy="Manage styles in Settings."
                  validationMessage={artStyleValidationMessage}
                  onModeChange={onArtStyleModeChange}
                  onTextChange={onArtStyleTextChange}
                />
              </Grid>
            </Stack>

            <Box
              borderWidth="1px"
              borderRadius="lg"
              p={4}
              bg="rgba(255,255,255,0.03)"
            >
              <Stack gap={4} h="full" justify="space-between">
                <Stack gap={2}>
                  <Text
                    fontSize="xs"
                    textTransform="uppercase"
                    color="fg.subtle"
                  >
                    This Run
                  </Text>
                  <Text fontSize="2xl" fontWeight="semibold">
                    {sceneCountSummary}
                  </Text>
                  <Text fontSize="sm" color="fg.muted">
                    {artStyleSummary}
                  </Text>
                  {hasActiveRun ? (
                    <Badge
                      colorScheme="blue"
                      variant="subtle"
                      alignSelf="start"
                    >
                      Pipeline currently running
                    </Badge>
                  ) : null}
                </Stack>

                <Stack gap={2}>
                  <Button
                    colorScheme="blue"
                    onClick={onLaunch}
                    loading={launching || hasActiveRun}
                    disabled={!canLaunch || artStyleValidationMessage !== null}
                    gap={2}
                    w="full"
                    size="lg"
                  >
                    <FiPlay />
                    {launchLabel}
                  </Button>
                  <Text
                    fontSize="sm"
                    color={!canLaunch ? "orange.300" : "fg.muted"}
                  >
                    {actionHelperText}
                  </Text>
                </Stack>
              </Stack>
            </Box>
          </Grid>

          <Box mt={5} pt={4} borderTopWidth="1px" borderColor="whiteAlpha.200">
            <Text
              fontSize="xs"
              textTransform="uppercase"
              color="fg.subtle"
              mb={2}
            >
              Pipeline Status
            </Text>
            {runSummary ? (
              <Stack gap={2}>
                <Flex wrap="wrap" gap={2} align="center">
                  <Badge colorScheme={statusColor(runSummary.status)}>
                    {runSummary.status}
                  </Badge>
                  {runSummary.stage_progress ? null : (
                    <Text
                      fontSize="sm"
                      color={
                        runSummary.status === "failed" ? "red.300" : "fg.muted"
                      }
                    >
                      {runSummary.status === "failed" ? "Failed at:" : "Stage:"}{" "}
                      {runSummary.current_stage ?? "—"}
                    </Text>
                  )}
                  <Text fontSize="sm" color="fg.muted">
                    Completed: {formatDateTime(runSummary.completed_at)}
                  </Text>
                  {usageText ? (
                    <Text fontSize="sm" color="fg.muted">
                      Usage: {usageText}
                    </Text>
                  ) : null}
                  {hasActiveRun ? (
                    <Badge colorScheme="blue" variant="subtle">
                      live
                    </Badge>
                  ) : null}
                </Flex>
                {runSummary.stage_progress ? (
                  <PipelineStageProgress
                    stageProgress={
                      runSummary.stage_progress as Record<string, StageEntry>
                    }
                  />
                ) : null}
                {runSummary.error_message ? (
                  <Text fontSize="sm" color="red.300">
                    {runSummary.error_message}
                  </Text>
                ) : null}
                {getUsageSummaryErrorMessages(
                  runSummary.usage_summary,
                  runSummary.error_message,
                ).map((msg, i) => (
                  <Text key={i} fontSize="sm" color="red.300">
                    {msg}
                  </Text>
                ))}
              </Stack>
            ) : (
              <Text fontSize="sm" color="fg.muted">
                No pipeline runs yet.
              </Text>
            )}
          </Box>
        </Box>
      </Stack>
    </Box>
  )
}

function StageBadge({
  label,
  count,
  status,
  error,
  showStatus = true,
}: {
  label: string
  count: number
  status: string
  error?: string | null
  showStatus?: boolean
}) {
  const badgeColor = showStatus
    ? stageStatusColor(status)
    : count > 0
      ? "blue"
      : "gray"

  return (
    <Box borderWidth="1px" borderRadius="md" p={3}>
      <Stack gap={1}>
        <HStack justify="space-between" align="center">
          <Text fontSize="sm" color="fg.muted">
            {label}
          </Text>
          <Badge colorScheme={badgeColor}>{count}</Badge>
        </HStack>
        {showStatus ? (
          <HStack justify="space-between" align="center">
            <Text fontSize="xs" color="fg.subtle" textTransform="uppercase">
              {formatStageStatus(status)}
            </Text>
            {error ? (
              <Text fontSize="xs" color="red.300" wordBreak="break-word">
                {error}
              </Text>
            ) : null}
          </HStack>
        ) : null}
      </Stack>
    </Box>
  )
}
