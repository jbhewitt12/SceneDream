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
import { type ArtStyle, SettingsApi } from "@/api/settings"
import useCustomToast from "@/hooks/useCustomToast"

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

const stageColor = (completed: boolean) => (completed ? "green" : "gray")

const isTerminalRunStatus = (status: string | null | undefined) =>
  status === "completed" || status === "failed"

const toEntryKey = (entry: DocumentDashboardEntry) =>
  entry.document_id ?? `${entry.slug}:${entry.source_path}`

function DocumentsPage() {
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [search, setSearch] = useState("")
  const [scenesPerRunByKey, setScenesPerRunByKey] = useState<
    Record<string, string>
  >({})
  const [artStyleByKey, setArtStyleByKey] = useState<Record<string, string>>({})
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
  const artStyles = settingsQuery.data?.art_styles ?? []

  useEffect(() => {
    const entries = dashboardQuery.data?.data
    if (!entries?.length) {
      return
    }

    setScenesPerRunByKey((previous) => {
      const next = { ...previous }
      for (const entry of entries) {
        const key = toEntryKey(entry)
        if (!(key in next)) {
          next[key] = String(defaultScenesPerRun)
        }
      }
      return next
    })

    setArtStyleByKey((previous) => {
      const next = { ...previous }
      for (const entry of entries) {
        const key = toEntryKey(entry)
        if (!(key in next)) {
          next[key] = ""
        }
      }
      return next
    })
  }, [dashboardQuery.data?.data, defaultScenesPerRun, toEntryKey])

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
            error instanceof Error
              ? error.message
              : "Failed to poll pipeline run status.",
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
    if (!term) {
      return rows
    }
    return rows.filter((row) =>
      [row.display_name, row.source_path, row.slug].some((value) =>
        value.toLowerCase().includes(term),
      ),
    )
  }, [dashboardQuery.data?.data, search])

  const handleLaunch = async (entry: DocumentDashboardEntry) => {
    const key = toEntryKey(entry)
    const scenesRaw = scenesPerRunByKey[key] ?? String(defaultScenesPerRun)
    const imagesForScenes = Number.parseInt(scenesRaw, 10)

    if (!Number.isFinite(imagesForScenes) || imagesForScenes <= 0) {
      showErrorToast("Scenes per run must be a positive integer.")
      return
    }

    setLaunchingByKey((previous) => ({
      ...previous,
      [key]: true,
    }))

    try {
      const selectedArtStyleId = artStyleByKey[key]
      const run = await PipelineRunsApi.start({
        document_id: entry.document_id ?? undefined,
        book_slug: entry.document_id ? undefined : entry.slug,
        book_path: entry.document_id ? undefined : entry.source_path,
        images_for_scenes: imagesForScenes,
        art_style_id: selectedArtStyleId ? selectedArtStyleId : undefined,
      })

      setActiveRunByKey((previous) => ({
        ...previous,
        [key]: run,
      }))

      showSuccessToast(`Pipeline run started for ${entry.display_name}.`)
      void dashboardQuery.refetch()
    } catch (error) {
      showErrorToast(
        error instanceof Error
          ? error.message
          : "Failed to launch pipeline run.",
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

        <HStack gap={3} align="stretch">
          <Box position="relative" flex="1">
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
          <Badge alignSelf="center" colorScheme="blue" px={3} py={1}>
            {filteredEntries.length} shown
          </Badge>
        </HStack>

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
              No documents matched your search or no files were found in
              `documents/`.
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
                artStyleOverrideValue={artStyleByKey[key] ?? ""}
                artStyles={artStyles}
                launching={launchingByKey[key] === true}
                onScenesPerRunChange={(value) =>
                  setScenesPerRunByKey((previous) => ({
                    ...previous,
                    [key]: value,
                  }))
                }
                onArtStyleOverrideChange={(value) =>
                  setArtStyleByKey((previous) => ({
                    ...previous,
                    [key]: value,
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
  usage_summary: Record<string, unknown>
  completed_at: string | null
}

function DocumentCard({
  entry,
  activeRun,
  scenesPerRunValue,
  artStyleOverrideValue,
  artStyles,
  launching,
  onScenesPerRunChange,
  onArtStyleOverrideChange,
  onLaunch,
}: {
  entry: DocumentDashboardEntry
  activeRun: PipelineRun | undefined
  scenesPerRunValue: string
  artStyleOverrideValue: string
  artStyles: ArtStyle[]
  launching: boolean
  onScenesPerRunChange: (value: string) => void
  onArtStyleOverrideChange: (value: string) => void
  onLaunch: () => void
}) {
  const runSummary: RunSummaryLike | null =
    activeRun ?? (entry.last_run ? { ...entry.last_run } : null)
  const usageText = runSummary
    ? formatUsageSummary(runSummary.usage_summary)
    : null
  const hasActiveRun =
    activeRun !== undefined && !isTerminalRunStatus(activeRun.status)
  const canLaunch = entry.file_exists || entry.stages.extracted

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
            complete={entry.stages.extracted}
          />
          <StageBadge
            label="Ranked"
            count={entry.counts.ranked}
            complete={entry.stages.ranked}
          />
          <StageBadge
            label="Prompts"
            count={entry.counts.prompts_generated}
            complete={entry.stages.prompts_generated}
          />
          <StageBadge
            label="Images"
            count={entry.counts.images_generated}
            complete={entry.stages.images_generated}
          />
        </Grid>

        <Box borderWidth="1px" borderRadius="md" p={3}>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            color="fg.subtle"
            mb={2}
          >
            Launch Pipeline
          </Text>
          <Grid templateColumns={{ base: "1fr", md: "1fr 1fr auto" }} gap={3}>
            <Box>
              <Text fontSize="sm" color="fg.muted" mb={1}>
                Scenes this run
              </Text>
              <Input
                type="number"
                min={1}
                value={scenesPerRunValue}
                onChange={(event) => onScenesPerRunChange(event.target.value)}
              />
            </Box>
            <Box>
              <Text fontSize="sm" color="fg.muted" mb={1}>
                Art style override
              </Text>
              <NativeSelectRoot w="full">
                <NativeSelectField
                  value={artStyleOverrideValue}
                  onChange={(event) =>
                    onArtStyleOverrideChange(event.target.value)
                  }
                >
                  <option value="">Use global default</option>
                  {artStyles.map((style) => (
                    <option key={style.id} value={style.id}>
                      {style.display_name}
                    </option>
                  ))}
                </NativeSelectField>
                <NativeSelectIndicator />
              </NativeSelectRoot>
            </Box>
            <Flex align="flex-end">
              <Button
                colorScheme="blue"
                onClick={onLaunch}
                loading={launching || hasActiveRun}
                disabled={!canLaunch}
                gap={2}
              >
                <FiPlay />
                Run pipeline
              </Button>
            </Flex>
          </Grid>
          {!canLaunch ? (
            <Text mt={2} fontSize="sm" color="orange.300">
              Source file is missing and no extracted scenes exist yet.
            </Text>
          ) : null}
        </Box>

        <Grid templateColumns={{ base: "1fr", md: "repeat(2, 1fr)" }} gap={3}>
          <Box borderWidth="1px" borderRadius="md" p={3}>
            <Text
              fontSize="xs"
              textTransform="uppercase"
              color="fg.subtle"
              mb={1}
            >
              Ingestion
            </Text>
            <HStack gap={2}>
              <Badge colorScheme={statusColor(entry.ingestion_state)}>
                {entry.ingestion_state ?? "unknown"}
              </Badge>
              {entry.ingestion_error ? (
                <Text fontSize="sm" color="red.300">
                  {entry.ingestion_error}
                </Text>
              ) : (
                <Text fontSize="sm" color="fg.muted">
                  No ingestion errors.
                </Text>
              )}
            </HStack>
          </Box>

          <Box borderWidth="1px" borderRadius="md" p={3}>
            <Text
              fontSize="xs"
              textTransform="uppercase"
              color="fg.subtle"
              mb={1}
            >
              Last Run
            </Text>
            {runSummary ? (
              <Stack gap={1}>
                <HStack gap={2}>
                  <Badge colorScheme={statusColor(runSummary.status)}>
                    {runSummary.status}
                  </Badge>
                  <Text fontSize="sm" color="fg.muted">
                    Stage: {runSummary.current_stage ?? "—"}
                  </Text>
                  {hasActiveRun ? (
                    <Badge colorScheme="blue" variant="subtle">
                      live
                    </Badge>
                  ) : null}
                </HStack>
                <Text fontSize="sm" color="fg.muted">
                  Completed: {formatDateTime(runSummary.completed_at)}
                </Text>
                {usageText ? (
                  <Text fontSize="sm" color="fg.muted">
                    Usage: {usageText}
                  </Text>
                ) : null}
                {runSummary.error_message ? (
                  <Text fontSize="sm" color="red.300">
                    {runSummary.error_message}
                  </Text>
                ) : null}
              </Stack>
            ) : (
              <Text fontSize="sm" color="fg.muted">
                No pipeline runs yet.
              </Text>
            )}
          </Box>
        </Grid>
      </Stack>
    </Box>
  )
}

function StageBadge({
  label,
  count,
  complete,
}: {
  label: string
  count: number
  complete: boolean
}) {
  return (
    <Box borderWidth="1px" borderRadius="md" p={3}>
      <HStack justify="space-between" align="center">
        <Text fontSize="sm" color="fg.muted">
          {label}
        </Text>
        <Badge colorScheme={stageColor(complete)}>{count}</Badge>
      </HStack>
    </Box>
  )
}
