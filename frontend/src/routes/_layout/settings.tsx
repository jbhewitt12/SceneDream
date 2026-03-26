import {
  AlertContent,
  AlertIndicator,
  AlertRoot,
  Box,
  Button,
  Container,
  Flex,
  Heading,
  Input,
  Spinner,
  Stack,
  Switch,
  Text,
  Textarea,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { SettingsApi, type SettingsConfigurationTest } from "@/api/settings"
import { PromptArtStyleControl } from "@/components/Common/PromptArtStyleControl"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type PromptArtStyleSelection,
  getPromptArtStyleSelectionFromSettings,
  getPromptArtStyleTextForPayload,
  getPromptArtStyleValidationMessage,
} from "@/types/promptArtStyle"
import { getDisplayErrorMessage } from "@/utils/apiErrors"

export const Route = createFileRoute("/_layout/settings")({
  component: SettingsPage,
})

const formatDateTime = (value: string) => {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}

const formatConfigurationStatus = (status: string) => {
  if (status === "passed") {
    return "Passed"
  }
  if (status === "warning") {
    return "Needs attention"
  }
  return "Failed"
}

const getConfigurationStatusColor = (status: string) => {
  if (status === "passed") {
    return "green.300"
  }
  if (status === "warning") {
    return "orange.300"
  }
  return "red.300"
}

const formatProviderLabel = (provider: string | null | undefined) => {
  if (provider === "openai") {
    return "OpenAI"
  }
  if (provider === "google") {
    return "Gemini"
  }
  if (provider === "openai_gpt_image") {
    return "OpenAI GPT Image"
  }
  return provider
}

function SettingsPage() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [scenesPerRun, setScenesPerRun] = useState<string>("")
  const [defaultPromptArtStyle, setDefaultPromptArtStyle] =
    useState<PromptArtStyleSelection>(() =>
      getPromptArtStyleSelectionFromSettings(undefined),
    )
  const [socialPostingEnabled, setSocialPostingEnabled] = useState(false)
  const [recommendedStylesText, setRecommendedStylesText] = useState<string>("")
  const [otherStylesText, setOtherStylesText] = useState<string>("")
  const [configurationTestResult, setConfigurationTestResult] =
    useState<SettingsConfigurationTest | null>(null)

  const settingsQuery = useQuery({
    queryKey: ["settings", "bundle"],
    queryFn: () => SettingsApi.get(),
  })
  const artStyleListsQuery = useQuery({
    queryKey: ["settings", "art-style-lists"],
    queryFn: () => SettingsApi.getArtStyleLists(),
  })

  useEffect(() => {
    if (!settingsQuery.data) {
      return
    }
    setScenesPerRun(String(settingsQuery.data.settings.default_scenes_per_run))
    setDefaultPromptArtStyle(
      getPromptArtStyleSelectionFromSettings(settingsQuery.data.settings),
    )
    setSocialPostingEnabled(settingsQuery.data.settings.social_posting_enabled)
  }, [settingsQuery.data])

  useEffect(() => {
    if (!artStyleListsQuery.data) {
      return
    }
    setRecommendedStylesText(
      artStyleListsQuery.data.recommended_styles.join("\n"),
    )
    setOtherStylesText(artStyleListsQuery.data.other_styles.join("\n"))
  }, [artStyleListsQuery.data])

  const parseStyleLines = (
    recommendedRaw: string,
    otherRaw: string,
  ): {
    recommended: string[]
    other: string[]
    recommendedDuplicates: string[]
    otherDuplicates: string[]
    crossListDuplicates: string[]
  } => {
    const slugify = (value: string) =>
      value
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")

    const parseLines = (value: string) =>
      value
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0)

    const recommended: string[] = []
    const recommendedDuplicates: string[] = []
    const recommendedSeen = new Set<string>()

    for (const line of parseLines(recommendedRaw)) {
      const slug = slugify(line) || "style"
      if (recommendedSeen.has(slug)) {
        recommendedDuplicates.push(line)
        continue
      }
      recommendedSeen.add(slug)
      recommended.push(line)
    }

    const other: string[] = []
    const otherDuplicates: string[] = []
    const crossListDuplicates: string[] = []
    const otherSeen = new Set<string>()

    for (const line of parseLines(otherRaw)) {
      const slug = slugify(line) || "style"
      if (recommendedSeen.has(slug)) {
        crossListDuplicates.push(line)
        continue
      }
      if (otherSeen.has(slug)) {
        otherDuplicates.push(line)
        continue
      }
      otherSeen.add(slug)
      other.push(line)
    }

    return {
      recommended,
      other,
      recommendedDuplicates,
      otherDuplicates,
      crossListDuplicates,
    }
  }

  const parsedStyleLists = parseStyleLines(
    recommendedStylesText,
    otherStylesText,
  )
  const hasEmptyCatalog =
    parsedStyleLists.recommended.length === 0 &&
    parsedStyleLists.other.length === 0
  const hasDuplicateOutcomes =
    parsedStyleLists.recommendedDuplicates.length > 0 ||
    parsedStyleLists.otherDuplicates.length > 0 ||
    parsedStyleLists.crossListDuplicates.length > 0
  const defaultPromptArtStyleValidationMessage =
    getPromptArtStyleValidationMessage(defaultPromptArtStyle)
  const savedDefaultPromptArtStyle = getPromptArtStyleSelectionFromSettings(
    settingsQuery.data?.settings,
  )
  const parsedScenesPerRun = Number.parseInt(scenesPerRun, 10)
  const scenesPerRunValidationMessage =
    scenesPerRun.length > 0 &&
    (!Number.isFinite(parsedScenesPerRun) || parsedScenesPerRun <= 0)
      ? "Scenes per run must be a positive integer."
      : null
  const pipelineDefaultsDirty =
    settingsQuery.data !== undefined &&
    (scenesPerRun !==
      String(settingsQuery.data.settings.default_scenes_per_run) ||
      defaultPromptArtStyle.promptArtStyleMode !==
        savedDefaultPromptArtStyle.promptArtStyleMode ||
      defaultPromptArtStyle.promptArtStyleText !==
        savedDefaultPromptArtStyle.promptArtStyleText)
  const artStyleListsDirty =
    artStyleListsQuery.data !== undefined &&
    (recommendedStylesText !==
      artStyleListsQuery.data.recommended_styles.join("\n") ||
      otherStylesText !== artStyleListsQuery.data.other_styles.join("\n"))

  const savePipelineDefaultsMutation = useMutation({
    mutationFn: async () => {
      if (scenesPerRunValidationMessage) {
        throw new Error(scenesPerRunValidationMessage)
      }
      if (!Number.isFinite(parsedScenesPerRun) || parsedScenesPerRun <= 0) {
        throw new Error("Scenes per run must be a positive integer.")
      }
      if (defaultPromptArtStyleValidationMessage) {
        throw new Error(defaultPromptArtStyleValidationMessage)
      }

      return SettingsApi.update({
        default_scenes_per_run: parsedScenesPerRun,
        default_prompt_art_style_mode: defaultPromptArtStyle.promptArtStyleMode,
        default_prompt_art_style_text: getPromptArtStyleTextForPayload(
          defaultPromptArtStyle,
        ),
      })
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(["settings", "bundle"], payload)
      setScenesPerRun(String(payload.settings.default_scenes_per_run))
      setDefaultPromptArtStyle(
        getPromptArtStyleSelectionFromSettings(payload.settings),
      )
      queryClient.invalidateQueries({ queryKey: ["settings", "bundle"] })
      showSuccessToast("Pipeline defaults updated.")
    },
    onError: (error) => {
      showErrorToast(
        getDisplayErrorMessage(error, "Failed to save pipeline defaults."),
      )
    },
  })

  const saveGeneralSettingsMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      SettingsApi.update({
        social_posting_enabled: enabled,
      }),
    onMutate: async (enabled) => {
      const previous =
        settingsQuery.data?.settings.social_posting_enabled ?? false
      setSocialPostingEnabled(enabled)
      return { previous }
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(["settings", "bundle"], payload)
      setSocialPostingEnabled(payload.settings.social_posting_enabled)
      queryClient.invalidateQueries({ queryKey: ["settings", "bundle"] })
      showSuccessToast("General settings updated.")
    },
    onError: (error, _enabled, context) => {
      setSocialPostingEnabled(context?.previous ?? false)
      showErrorToast(
        getDisplayErrorMessage(error, "Failed to save general settings."),
      )
    },
  })

  const saveArtStyleListsMutation = useMutation({
    mutationFn: async () => {
      if (hasEmptyCatalog) {
        throw new Error(
          "At least one style is required across Recommended and Other lists.",
        )
      }

      return SettingsApi.updateArtStyleLists({
        recommended_styles: parsedStyleLists.recommended,
        other_styles: parsedStyleLists.other,
      })
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(["settings", "art-style-lists"], payload)
      setRecommendedStylesText(payload.recommended_styles.join("\n"))
      setOtherStylesText(payload.other_styles.join("\n"))
      queryClient.invalidateQueries({ queryKey: ["settings", "bundle"] })
      queryClient.invalidateQueries({
        queryKey: ["settings", "art-style-lists"],
      })
      showSuccessToast("Art style lists updated.")
    },
    onError: (error) => {
      showErrorToast(
        getDisplayErrorMessage(error, "Failed to save art style lists."),
      )
    },
  })

  const resetToDefaultsMutation = useMutation({
    mutationFn: () => SettingsApi.resetArtStyleLists(),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings", "art-style-lists"], data)
      setRecommendedStylesText(data.recommended_styles.join("\n"))
      setOtherStylesText(data.other_styles.join("\n"))
      showSuccessToast("Art style lists reset to defaults.")
    },
    onError: (error) => {
      showErrorToast(
        getDisplayErrorMessage(error, "Failed to reset art style lists."),
      )
    },
  })

  const testConfigurationMutation = useMutation({
    mutationFn: () => SettingsApi.testConfiguration(),
    onSuccess: (payload) => {
      setConfigurationTestResult(payload)
      if (payload.ready_for_pipeline) {
        showSuccessToast(payload.summary)
        return
      }
      showErrorToast(payload.summary)
    },
    onError: (error) => {
      showErrorToast(
        getDisplayErrorMessage(error, "Failed to test pipeline configuration."),
      )
    },
  })

  const handlePipelineDefaultsReset = () => {
    if (!settingsQuery.data) {
      return
    }
    setScenesPerRun(String(settingsQuery.data.settings.default_scenes_per_run))
    setDefaultPromptArtStyle(
      getPromptArtStyleSelectionFromSettings(settingsQuery.data.settings),
    )
  }

  const handleArtStyleListsReset = () => {
    if (!artStyleListsQuery.data) {
      return
    }
    setRecommendedStylesText(
      artStyleListsQuery.data.recommended_styles.join("\n"),
    )
    setOtherStylesText(artStyleListsQuery.data.other_styles.join("\n"))
  }

  const isLoading = settingsQuery.isLoading || artStyleListsQuery.isLoading
  const queryError = settingsQuery.error ?? artStyleListsQuery.error

  return (
    <Container maxW="4xl" py={6}>
      <Stack gap={6}>
        <Heading size="lg">Settings</Heading>
        <Text color="fg.muted">
          Configure pipeline defaults, prompt-style sampling, and optional
          posting features.
        </Text>

        {isLoading ? (
          <Flex justify="center" py={12}>
            <Spinner size="lg" />
          </Flex>
        ) : null}

        {queryError ? (
          <AlertRoot status="error">
            <AlertIndicator />
            <AlertContent>
              {queryError instanceof Error
                ? getDisplayErrorMessage(queryError, "Failed to load settings.")
                : "Failed to load settings."}
            </AlertContent>
          </AlertRoot>
        ) : null}

        {settingsQuery.data && artStyleListsQuery.data ? (
          <>
            <Box
              p={5}
              borderWidth="1px"
              borderRadius="lg"
              bg="rgba(255,255,255,0.04)"
              backdropFilter="blur(8px) saturate(140%)"
            >
              <Stack gap={4}>
                <Heading size="sm">Pipeline Defaults</Heading>
                <Box>
                  <Text
                    textTransform="uppercase"
                    fontSize="xs"
                    color="fg.subtle"
                    mb={1}
                  >
                    Default scenes per run
                  </Text>
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    value={scenesPerRun}
                    onChange={(event) => setScenesPerRun(event.target.value)}
                  />
                  {scenesPerRunValidationMessage ? (
                    <Text mt={2} fontSize="sm" color="red.300">
                      {scenesPerRunValidationMessage}
                    </Text>
                  ) : null}
                </Box>

                <Box>
                  <PromptArtStyleControl
                    label="Default art style"
                    selection={defaultPromptArtStyle}
                    recommendedCount={parsedStyleLists.recommended.length}
                    otherCount={parsedStyleLists.other.length}
                    randomMixManageCopy="Manage styles below in Settings."
                    validationMessage={defaultPromptArtStyleValidationMessage}
                    onModeChange={(promptArtStyleMode) =>
                      setDefaultPromptArtStyle((previous) => ({
                        ...previous,
                        promptArtStyleMode,
                      }))
                    }
                    onTextChange={(promptArtStyleText) =>
                      setDefaultPromptArtStyle((previous) => ({
                        ...previous,
                        promptArtStyleText,
                      }))
                    }
                    labelColor="fg.subtle"
                    labelFontSize="xs"
                    labelTextTransform="uppercase"
                  />
                </Box>

                <Text fontSize="sm" color="fg.muted">
                  Last updated:{" "}
                  {formatDateTime(settingsQuery.data.settings.updated_at)}
                </Text>
                <Flex justify="flex-end" gap={2}>
                  <Button
                    variant="ghost"
                    onClick={handlePipelineDefaultsReset}
                    disabled={!pipelineDefaultsDirty}
                  >
                    Reset
                  </Button>
                  <Button
                    colorScheme="blue"
                    onClick={() => savePipelineDefaultsMutation.mutate()}
                    loading={savePipelineDefaultsMutation.isPending}
                    disabled={
                      !pipelineDefaultsDirty ||
                      scenesPerRunValidationMessage !== null ||
                      defaultPromptArtStyleValidationMessage !== null
                    }
                  >
                    Save pipeline defaults
                  </Button>
                </Flex>
              </Stack>
            </Box>

            <Box
              p={5}
              borderWidth="1px"
              borderRadius="lg"
              bg="rgba(255,255,255,0.04)"
              backdropFilter="blur(8px) saturate(140%)"
            >
              <Stack gap={4}>
                <Heading size="sm">Test Configuration</Heading>
                <Text fontSize="sm" color="fg.muted">
                  Run lightweight provider checks before your first pipeline
                  run. This verifies the configured LLM models can authenticate
                  and respond, and it validates the default image provider
                  locally without generating a billed test image.
                </Text>

                <Flex
                  justify="space-between"
                  align="center"
                  gap={4}
                  wrap="wrap"
                >
                  <Text fontSize="sm" color="fg.muted">
                    Use{" "}
                    <Text as="span" fontFamily="mono" color="fg.default">
                      http://localhost:5173
                    </Text>{" "}
                    as the canonical local URL. The direct-run dev setup now
                    uses the Vite proxy so localhost and 127.0.0.1 loopback
                    mixes do not trip CORS in the common path.
                  </Text>
                  <Button
                    colorScheme="blue"
                    onClick={() => testConfigurationMutation.mutate()}
                    loading={testConfigurationMutation.isPending}
                  >
                    Run configuration test
                  </Button>
                </Flex>

                {configurationTestResult ? (
                  <Box p={4} borderWidth="1px" borderRadius="md" bg="bg.subtle">
                    <Stack gap={4}>
                      <Box>
                        <Text
                          textTransform="uppercase"
                          fontSize="xs"
                          color="fg.subtle"
                        >
                          Latest result
                        </Text>
                        <Text
                          mt={1}
                          fontWeight="semibold"
                          color={getConfigurationStatusColor(
                            configurationTestResult.status,
                          )}
                        >
                          {formatConfigurationStatus(
                            configurationTestResult.status,
                          )}
                        </Text>
                        <Text mt={2} fontSize="sm" color="fg.muted">
                          {configurationTestResult.summary}
                        </Text>
                        <Text mt={2} fontSize="sm" color="fg.muted">
                          Last checked:{" "}
                          {formatDateTime(configurationTestResult.checked_at)}
                        </Text>
                      </Box>

                      <Stack gap={3}>
                        {configurationTestResult.checks.map((check) => (
                          <Box
                            key={check.key}
                            p={4}
                            borderWidth="1px"
                            borderRadius="md"
                            borderColor={getConfigurationStatusColor(
                              check.status,
                            )}
                          >
                            <Stack gap={2}>
                              <Flex
                                justify="space-between"
                                align="flex-start"
                                gap={4}
                                wrap="wrap"
                              >
                                <Box>
                                  <Text
                                    textTransform="uppercase"
                                    fontSize="xs"
                                    color="fg.subtle"
                                  >
                                    {check.label}
                                  </Text>
                                  <Text
                                    mt={1}
                                    fontWeight="semibold"
                                    color={getConfigurationStatusColor(
                                      check.status,
                                    )}
                                  >
                                    {formatConfigurationStatus(check.status)}
                                  </Text>
                                </Box>
                                <Text fontSize="sm" color="fg.muted">
                                  {formatProviderLabel(check.provider) ||
                                    "No provider"}
                                  {check.model ? ` · ${check.model}` : ""}
                                  {check.used_backup_model
                                    ? " · backup model"
                                    : ""}
                                  {check.latency_ms !== null
                                    ? ` · ${check.latency_ms} ms`
                                    : ""}
                                </Text>
                              </Flex>

                              <Text fontSize="sm">{check.message}</Text>

                              {check.hint ? (
                                <Text fontSize="sm" color="fg.muted">
                                  Next step: {check.hint}
                                </Text>
                              ) : null}

                              {(check.action_items?.length ?? 0) > 0 ? (
                                <Stack gap={1}>
                                  {check.action_items?.map((item) => (
                                    <Text
                                      key={`${check.key}-${item}`}
                                      fontSize="sm"
                                      color="fg.muted"
                                    >
                                      - {item}
                                    </Text>
                                  ))}
                                </Stack>
                              ) : null}

                              {(check.cause_messages?.length ?? 0) > 0 ? (
                                <Stack gap={1}>
                                  {check.cause_messages
                                    ?.slice(0, 2)
                                    .map((message, index) => (
                                      <Text
                                        key={`${check.key}-cause-${index}`}
                                        fontSize="sm"
                                        color="fg.muted"
                                        fontFamily="mono"
                                      >
                                        {message}
                                      </Text>
                                    ))}
                                </Stack>
                              ) : null}
                            </Stack>
                          </Box>
                        ))}
                      </Stack>
                    </Stack>
                  </Box>
                ) : null}
              </Stack>
            </Box>

            <Box
              p={5}
              borderWidth="1px"
              borderRadius="lg"
              bg="rgba(255,255,255,0.04)"
              backdropFilter="blur(8px) saturate(140%)"
            >
              <Stack gap={4}>
                <Heading size="sm">Random Style Mix</Heading>
                <Text fontSize="sm" color="fg.muted">
                  Enter one style per line.
                </Text>
                <Box p={3} borderWidth="1px" borderRadius="md" bg="bg.subtle">
                  <Text fontSize="sm" color="fg.muted">
                    Random Style Mix samples from both lists, weighted toward
                    Recommended styles, and passes that mix into prompt
                    generation so each run can explore a range of visual
                    directions. We generate multiple images for each scene, with
                    a different style for each image.
                  </Text>
                </Box>
                <Box>
                  <Text
                    textTransform="uppercase"
                    fontSize="xs"
                    color="fg.subtle"
                    mb={1}
                  >
                    Recommended Styles
                  </Text>
                  <Textarea
                    value={recommendedStylesText}
                    onChange={(event) =>
                      setRecommendedStylesText(event.target.value)
                    }
                    minH="240px"
                    resize="vertical"
                    fontFamily="mono"
                  />
                </Box>
                <Box>
                  <Text
                    textTransform="uppercase"
                    fontSize="xs"
                    color="fg.subtle"
                    mb={1}
                  >
                    Other Styles
                  </Text>
                  <Textarea
                    value={otherStylesText}
                    onChange={(event) => setOtherStylesText(event.target.value)}
                    minH="240px"
                    resize="vertical"
                    fontFamily="mono"
                  />
                </Box>
                {hasEmptyCatalog ? (
                  <AlertRoot status="error">
                    <AlertIndicator />
                    <AlertContent>
                      At least one style is required across Recommended and
                      Other lists.
                    </AlertContent>
                  </AlertRoot>
                ) : null}
                {hasDuplicateOutcomes ? (
                  <AlertRoot status="warning">
                    <AlertIndicator />
                    <AlertContent>
                      Duplicate entries were detected and will be deduplicated
                      on save. If a style appears in both lists, Recommended
                      wins.
                    </AlertContent>
                  </AlertRoot>
                ) : null}
                <Flex justify="flex-end" gap={2} wrap="wrap">
                  <Button
                    variant="ghost"
                    onClick={handleArtStyleListsReset}
                    disabled={!artStyleListsDirty}
                  >
                    Reset
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => resetToDefaultsMutation.mutate()}
                    loading={resetToDefaultsMutation.isPending}
                  >
                    Reset to defaults
                  </Button>
                  <Button
                    colorScheme="blue"
                    onClick={() => saveArtStyleListsMutation.mutate()}
                    loading={saveArtStyleListsMutation.isPending}
                    disabled={!artStyleListsDirty || hasEmptyCatalog}
                  >
                    Save styles
                  </Button>
                </Flex>
                <Text fontSize="sm" color="fg.muted">
                  Last updated:{" "}
                  {formatDateTime(artStyleListsQuery.data.updated_at)}
                </Text>
              </Stack>
            </Box>

            <Box
              p={5}
              borderWidth="1px"
              borderRadius="lg"
              bg="rgba(255,255,255,0.04)"
              backdropFilter="blur(8px) saturate(140%)"
            >
              <Stack gap={4}>
                <Heading size="sm">General</Heading>
                <Box p={4} borderWidth="1px" borderRadius="md" bg="bg.subtle">
                  <Flex align="center" justify="space-between" gap={4}>
                    <Box>
                      <Text
                        textTransform="uppercase"
                        fontSize="xs"
                        color="fg.subtle"
                      >
                        Social media posting
                      </Text>
                      <Text fontSize="sm" color="fg.muted" mt={1}>
                        Enable posting actions and status in Generated Images.
                        Disabling this hides those surfaces outside Settings and
                        pauses background posting work. Changes save
                        immediately.
                      </Text>
                    </Box>
                    <Switch.Root
                      checked={socialPostingEnabled}
                      disabled={saveGeneralSettingsMutation.isPending}
                      onCheckedChange={(event) => {
                        saveGeneralSettingsMutation.mutate(event.checked)
                      }}
                    >
                      <Switch.HiddenInput />
                      <Switch.Control />
                    </Switch.Root>
                  </Flex>
                </Box>

                <Text fontSize="sm" color="fg.muted">
                  Last updated:{" "}
                  {formatDateTime(settingsQuery.data.settings.updated_at)}
                </Text>
              </Stack>
            </Box>
          </>
        ) : null}
      </Stack>
    </Container>
  )
}
