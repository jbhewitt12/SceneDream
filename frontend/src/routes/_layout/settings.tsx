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
  NativeSelectField,
  NativeSelectIndicator,
  NativeSelectRoot,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect, useState } from "react"

import { SettingsApi } from "@/api/settings"
import useCustomToast from "@/hooks/useCustomToast"

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
  const [defaultArtStyleId, setDefaultArtStyleId] = useState<string>("")

  const settingsQuery = useQuery({
    queryKey: ["settings", "bundle"],
    queryFn: () => SettingsApi.get(),
  })

  useEffect(() => {
    if (!settingsQuery.data) {
      return
    }
    setScenesPerRun(String(settingsQuery.data.settings.default_scenes_per_run))
    setDefaultArtStyleId(settingsQuery.data.settings.default_art_style_id ?? "")
  }, [settingsQuery.data])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const parsedScenes = Number.parseInt(scenesPerRun, 10)
      if (!Number.isFinite(parsedScenes) || parsedScenes <= 0) {
        throw new Error("Scenes per run must be a positive integer.")
      }
      return SettingsApi.update({
        default_scenes_per_run: parsedScenes,
        default_art_style_id: defaultArtStyleId || null,
      })
    },
    onSuccess: (payload) => {
      queryClient.setQueryData(["settings", "bundle"], payload)
      showSuccessToast("Settings updated.")
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : "Failed to save settings."
      showErrorToast(message)
    },
  })

  const handleReset = () => {
    if (!settingsQuery.data) {
      return
    }
    setScenesPerRun(String(settingsQuery.data.settings.default_scenes_per_run))
    setDefaultArtStyleId(settingsQuery.data.settings.default_art_style_id ?? "")
  }

  const isDirty =
    settingsQuery.data !== undefined &&
    (scenesPerRun !== String(settingsQuery.data.settings.default_scenes_per_run) ||
      defaultArtStyleId !== (settingsQuery.data.settings.default_art_style_id ?? ""))

  return (
    <Container maxW="4xl" py={6}>
      <Stack gap={6}>
        <Heading size="lg">Settings</Heading>
        <Text color="fg.muted">
          Configure defaults used by pipeline runs and prompt-style sampling.
        </Text>

        {settingsQuery.isLoading ? (
          <Flex justify="center" py={12}>
            <Spinner size="lg" />
          </Flex>
        ) : null}

        {settingsQuery.error ? (
          <AlertRoot status="error">
            <AlertIndicator />
            <AlertContent>
              {settingsQuery.error instanceof Error
                ? settingsQuery.error.message
                : "Failed to load settings."}
            </AlertContent>
          </AlertRoot>
        ) : null}

        {settingsQuery.data ? (
          <Box
            p={5}
            borderWidth="1px"
            borderRadius="lg"
            bg="rgba(255,255,255,0.04)"
            backdropFilter="blur(8px) saturate(140%)"
          >
            <Stack gap={4}>
              <Box>
                <Text textTransform="uppercase" fontSize="xs" color="fg.subtle" mb={1}>
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
                <Text textTransform="uppercase" fontSize="xs" color="fg.subtle" mb={1}>
                  Default art style
                </Text>
                <NativeSelectRoot w="full">
                  <NativeSelectField
                    value={defaultArtStyleId}
                    onChange={(event) => setDefaultArtStyleId(event.target.value)}
                  >
                    <option value="">No default</option>
                    {settingsQuery.data.art_styles.map((style) => (
                      <option key={style.id} value={style.id}>
                        {style.display_name}
                      </option>
                    ))}
                  </NativeSelectField>
                  <NativeSelectIndicator />
                </NativeSelectRoot>
              </Box>

              <Text fontSize="sm" color="fg.muted">
                Last updated: {formatDateTime(settingsQuery.data.settings.updated_at)}
              </Text>

              <Flex justify="flex-end" gap={2}>
                <Button variant="ghost" onClick={handleReset} disabled={!isDirty}>
                  Reset
                </Button>
                <Button
                  colorScheme="blue"
                  onClick={() => saveMutation.mutate()}
                  loading={saveMutation.isPending}
                  disabled={!isDirty}
                >
                  Save settings
                </Button>
              </Flex>
            </Stack>
          </Box>
        ) : null}
      </Stack>
    </Container>
  )
}
