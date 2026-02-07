import {
  Box,
  Button,
  Container,
  Flex,
  HStack,
  Heading,
  Icon,
  Input,
  Separator,
  SimpleGrid,
  Stack,
  Switch,
  Text,
} from "@chakra-ui/react"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  Link as RouterLink,
  createFileRoute,
  useNavigate,
} from "@tanstack/react-router"
import { useMemo } from "react"
import { FiArrowLeft, FiFilter, FiRefreshCcw, FiZap } from "react-icons/fi"
import { z } from "zod"

import { ImagePromptGenerationApi } from "@/api/imagePromptGeneration"
import { ImagePromptApi } from "@/api/imagePrompts"
import type { ImagePromptSceneSummary } from "@/client"
import {
  PromptDetailDrawer,
  PromptList,
  SceneContextPanel,
} from "@/components/Prompts"
import useCustomToast from "@/hooks/useCustomToast"

const scenePromptsSearchSchema = z.object({
  model_name: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  prompt_version: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  limit: z.coerce.number().int().min(1).max(100).catch(20),
  newest_first: z
    .enum(["true", "false"])
    .transform((value) => value === "true")
    .catch(true),
  include_scene: z
    .enum(["true", "false"])
    .transform((value) => value === "true")
    .catch(true),
})

type ScenePromptsSearch = z.infer<typeof scenePromptsSearchSchema>

type FilterUpdater = (updates: Partial<ScenePromptsSearch>) => void

const ScenePromptFilters = ({
  search,
  onChange,
}: {
  search: ScenePromptsSearch
  onChange: FilterUpdater
}) => {
  const handleChange = (updates: Partial<ScenePromptsSearch>) =>
    onChange({ ...updates })

  const resetFilters = () =>
    onChange({
      model_name: undefined,
      prompt_version: undefined,
      newest_first: true,
    })

  return (
    <Stack
      gap={4}
      p={4}
      borderWidth="1px"
      borderRadius="lg"
      bg="bg.surface"
      shadow="sm"
    >
      <Flex align="center" justify="space-between">
        <HStack gap={2}>
          <Icon as={FiFilter} />
          <Heading size="sm">Scene prompt filters</Heading>
        </HStack>
        <Button size="sm" variant="ghost" gap={2} onClick={resetFilters}>
          <Icon as={FiRefreshCcw} />
          Reset
        </Button>
      </Flex>
      <SimpleGrid columns={{ base: 1, md: 3 }} gap={4}>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Model
          </Text>
          <Input
            placeholder="gemini-2.5-pro"
            value={search.model_name ?? ""}
            onChange={(event) =>
              handleChange({
                model_name: event.target.value.trim() || undefined,
              })
            }
          />
        </Stack>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Prompt version
          </Text>
          <Input
            placeholder="image-prompts-v1"
            value={search.prompt_version ?? ""}
            onChange={(event) =>
              handleChange({
                prompt_version: event.target.value.trim() || undefined,
              })
            }
          />
        </Stack>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Max variants
          </Text>
          <Input
            type="number"
            min="1"
            max="100"
            value={search.limit}
            onChange={(event) =>
              handleChange({ limit: Number.parseInt(event.target.value, 10) })
            }
          />
        </Stack>
        <Stack
          spacing={1}
          direction="row"
          align="center"
          justify="space-between"
        >
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Newest first
          </Text>
          <Switch
            checked={search.newest_first}
            onChange={(event) =>
              handleChange({
                newest_first: (event.target as HTMLInputElement).checked,
              })
            }
          />
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}

export const Route = createFileRoute("/_layout/scene-prompts/$sceneId")({
  component: ScenePromptsPage,
  validateSearch: (search) => scenePromptsSearchSchema.parse(search),
})

function ScenePromptsPage() {
  const { sceneId } = Route.useParams()
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const handleSearchUpdate = (updates: Partial<ScenePromptsSearch>) => {
    navigate({
      search: (prev) => ({
        ...prev,
        ...updates,
      }),
    })
  }

  const promptQuery = useQuery({
    queryKey: ["image-prompts", "scene", { sceneId, search }],
    queryFn: () =>
      ImagePromptApi.listForScene({
        sceneId,
        limit: search.limit,
        modelName: search.model_name ?? undefined,
        promptVersion: search.prompt_version ?? undefined,
        newestFirst: search.newest_first,
        includeScene: search.include_scene,
      }),
    placeholderData: (previousData) => previousData,
  })

  const prompts = promptQuery.data?.data ?? []
  const sceneSummary: ImagePromptSceneSummary | undefined = useMemo(() => {
    if (prompts.length && prompts[0]?.scene) {
      return prompts[0].scene ?? undefined
    }
    const meta = promptQuery.data?.meta
    if (meta && typeof meta === "object" && "scene" in meta) {
      const value = (meta as Record<string, unknown>).scene
      if (value && typeof value === "object") {
        return value as ImagePromptSceneSummary
      }
    }
    return undefined
  }, [prompts, promptQuery.data?.meta])

  const generationMutation = useMutation({
    mutationFn: () =>
      ImagePromptGenerationApi.triggerForScene({
        sceneId,
        modelName: search.model_name ?? undefined,
        promptVersion: search.prompt_version ?? undefined,
      }),
    onSuccess: () => {
      showSuccessToast("Prompt generation triggered for scene.")
    },
    onError: (error) => {
      showErrorToast(
        error instanceof Error
          ? error.message
          : "Unable to trigger prompts for this scene",
      )
    },
  })

  const disableGenerate = generationMutation.isPending

  return (
    <Container maxW="4xl" py={4} display="flex" flexDirection="column" gap={4}>
      <Flex align="center" justify="space-between" gap={4} flexWrap="wrap">
        <Heading size="lg">Scene prompts</Heading>
        <HStack gap={2}>
          <RouterLink
            to="/prompt-gallery"
            search={
              sceneSummary?.book_slug
                ? { book_slug: sceneSummary.book_slug }
                : undefined
            }
          >
            <Button size="sm" variant="ghost" gap={1}>
              <Icon as={FiArrowLeft} />
              Back to gallery
            </Button>
          </RouterLink>
          <Button
            colorScheme="purple"
            onClick={() => generationMutation.mutate()}
            loading={generationMutation.isPending}
            disabled={disableGenerate}
            gap={1}
          >
            <Icon as={FiZap} />
            Generate prompts
          </Button>
        </HStack>
      </Flex>
      {sceneSummary && (
        <SceneContextPanel
          scene={sceneSummary}
          contextWindow={
            prompts[0]?.context_window ?? {
              chapterNumber: sceneSummary.chapter_number,
              paragraphSpan: null,
              paragraphsBefore: null,
              paragraphsAfter: null,
            }
          }
        />
      )}
      <ScenePromptFilters search={search} onChange={handleSearchUpdate} />
      <Separator />
      <PromptList
        prompts={prompts}
        isLoading={promptQuery.isLoading && !promptQuery.isPlaceholderData}
        height="calc(100vh - 360px)"
        emptyState={<Text>No prompts found for this scene yet.</Text>}
      />
      {/* Detail drawer retained for scene context – keeping as-is */}
    </Container>
  )
}
