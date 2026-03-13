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
  Text,
  Textarea,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { SettingsApi } from "@/api/settings"
import { PromptArtStyleControl } from "@/components/Common/PromptArtStyleControl"
import useCustomToast from "@/hooks/useCustomToast"
import {
  type PromptArtStyleSelection,
  getPromptArtStyleSelectionFromSettings,
  getPromptArtStyleTextForPayload,
  getPromptArtStyleValidationMessage,
} from "@/types/promptArtStyle"

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

function SettingsPage() {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [scenesPerRun, setScenesPerRun] = useState<string>("")
  const [defaultPromptArtStyle, setDefaultPromptArtStyle] =
    useState<PromptArtStyleSelection>(() =>
      getPromptArtStyleSelectionFromSettings(undefined),
    )
  const [recommendedStylesText, setRecommendedStylesText] = useState<string>("")
  const [otherStylesText, setOtherStylesText] = useState<string>("")

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

  const saveMutation = useMutation({
    mutationFn: async () => {
      const parsedScenes = Number.parseInt(scenesPerRun, 10)
      if (!Number.isFinite(parsedScenes) || parsedScenes <= 0) {
        throw new Error("Scenes per run must be a positive integer.")
      }
      if (hasEmptyCatalog) {
        throw new Error(
          "At least one style is required across Recommended and Other lists.",
        )
      }
      if (defaultPromptArtStyleValidationMessage) {
        throw new Error(defaultPromptArtStyleValidationMessage)
      }

      const settingsResponse = await SettingsApi.update({
        default_scenes_per_run: parsedScenes,
        default_prompt_art_style_mode: defaultPromptArtStyle.promptArtStyleMode,
        default_prompt_art_style_text: getPromptArtStyleTextForPayload(
          defaultPromptArtStyle,
        ),
      })
      const listsResponse = await SettingsApi.updateArtStyleLists({
        recommended_styles: parsedStyleLists.recommended,
        other_styles: parsedStyleLists.other,
      })
      return { settingsResponse, listsResponse }
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(["settings", "bundle"], payload.settingsResponse)
      queryClient.setQueryData(
        ["settings", "art-style-lists"],
        payload.listsResponse,
      )
      setScenesPerRun(
        String(payload.settingsResponse.settings.default_scenes_per_run),
      )
      setDefaultPromptArtStyle(
        getPromptArtStyleSelectionFromSettings(
          payload.settingsResponse.settings,
        ),
      )
      setRecommendedStylesText(
        payload.listsResponse.recommended_styles.join("\n"),
      )
      setOtherStylesText(payload.listsResponse.other_styles.join("\n"))
      queryClient.invalidateQueries({ queryKey: ["settings", "bundle"] })
      showSuccessToast("Settings updated.")
    },
    onError: (error) => {
      const message =
        error instanceof Error ? error.message : "Failed to save settings."
      showErrorToast(message)
    },
  })

  const handleReset = () => {
    if (!settingsQuery.data || !artStyleListsQuery.data) {
      return
    }
    setScenesPerRun(String(settingsQuery.data.settings.default_scenes_per_run))
    setDefaultPromptArtStyle(
      getPromptArtStyleSelectionFromSettings(settingsQuery.data.settings),
    )
    setRecommendedStylesText(
      artStyleListsQuery.data.recommended_styles.join("\n"),
    )
    setOtherStylesText(artStyleListsQuery.data.other_styles.join("\n"))
  }

  const isDirty =
    settingsQuery.data !== undefined &&
    artStyleListsQuery.data !== undefined &&
    (scenesPerRun !==
      String(settingsQuery.data.settings.default_scenes_per_run) ||
      defaultPromptArtStyle.promptArtStyleMode !==
        savedDefaultPromptArtStyle.promptArtStyleMode ||
      defaultPromptArtStyle.promptArtStyleText !==
        savedDefaultPromptArtStyle.promptArtStyleText ||
      recommendedStylesText !==
        artStyleListsQuery.data.recommended_styles.join("\n") ||
      otherStylesText !== artStyleListsQuery.data.other_styles.join("\n"))

  const isLoading = settingsQuery.isLoading || artStyleListsQuery.isLoading
  const queryError = settingsQuery.error ?? artStyleListsQuery.error

  return (
    <Container maxW="4xl" py={6}>
      <Stack gap={6}>
        <Heading size="lg">Settings</Heading>
        <Text color="fg.muted">
          Configure defaults used by pipeline runs and prompt-style sampling.
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
                ? queryError.message
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
                <Heading size="sm">Art Styles</Heading>
                <Text fontSize="sm" color="fg.muted">
                  Enter one style per line.
                </Text>
                <Box p={3} borderWidth="1px" borderRadius="md" bg="bg.subtle">
                  <Text fontSize="sm" color="fg.muted">
                    Random Style Mix samples from both lists, weighted toward
                    Recommended styles, and passes that mix into prompt
                    generation so each run can explore a range of visual
                    directions.
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
                <Text fontSize="sm" color="fg.muted">
                  Last updated:{" "}
                  {formatDateTime(artStyleListsQuery.data.updated_at)}
                </Text>
              </Stack>
            </Box>

            <Flex justify="flex-end" gap={2}>
              <Button variant="ghost" onClick={handleReset} disabled={!isDirty}>
                Reset
              </Button>
              <Button
                colorScheme="blue"
                onClick={() => saveMutation.mutate()}
                loading={saveMutation.isPending}
                disabled={
                  !isDirty ||
                  hasEmptyCatalog ||
                  defaultPromptArtStyleValidationMessage !== null
                }
              >
                Save settings
              </Button>
            </Flex>
          </>
        ) : null}
      </Stack>
    </Container>
  )
}
