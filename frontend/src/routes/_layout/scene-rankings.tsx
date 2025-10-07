import {
  AccordionItem,
  AccordionItemContent,
  AccordionItemIndicator,
  AccordionItemTrigger,
  AccordionRoot,
  AlertContent,
  AlertIndicator,
  AlertRoot,
  Badge,
  Box,
  Button,
  Container,
  Flex,
  HStack,
  Heading,
  Icon,
  Input,
  NativeSelectField,
  NativeSelectIndicator,
  NativeSelectRoot,
  Separator,
  SimpleGrid,
  Spinner,
  Stack,
  TagRoot,
  TagLabel,
  Text,
  VStack,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo } from "react"
import {
  FiAlertTriangle,
  FiFilter,
  FiRefreshCcw,
  FiSearch,
} from "react-icons/fi"
import { FiTrendingUp } from "react-icons/fi"
import { z } from "zod"

import { SceneExtractionService } from "@/api/sceneExtractions"
import {
  type SceneRanking,
  SceneRankingService,
  type SceneRankingTopParams,
} from "@/api/sceneRankings"

const sceneRankingSearchSchema = z.object({
  book_slug: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  limit: z.coerce.number().int().min(1).max(100).catch(10),
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
  weight_config_hash: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  include_scene: z
    .enum(["true", "false"])
    .transform((value) => value === "true")
    .optional()
    .catch(true),
  sort: z.enum(["asc", "desc"]).catch("desc"),
})

type SceneRankingSearch = z.infer<typeof sceneRankingSearchSchema>

type FilterUpdater = (updates: Partial<SceneRankingSearch>) => void

export const Route = createFileRoute("/_layout/scene-rankings")({
  component: SceneRankingsPage,
  validateSearch: (search) => sceneRankingSearchSchema.parse(search),
})

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "—"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)
}

const toTitleCase = (value: string) =>
  value
    .split("_")
    .map((segment) =>
      segment.length
        ? segment[0].toUpperCase() + segment.slice(1).toLowerCase()
        : segment,
    )
    .join(" ")

const truncateText = (value: string, maxLength = 300) => {
  if (value.length <= maxLength) {
    return value
  }
  const truncated = value.slice(0, maxLength).trimEnd()
  return `${truncated}…`
}

const SceneRankingFilters = ({
  search,
  onChange,
  availableBooks,
  isFetching,
}: {
  search: SceneRankingSearch
  onChange: FilterUpdater
  availableBooks: string[]
  isFetching: boolean
}) => {
  const includeScene = search.include_scene ?? true

  const handleChange = (patch: Partial<SceneRankingSearch>) => {
    onChange(patch)
  }

  const resetFilters = () => {
    handleChange({
      limit: 10,
      model_name: undefined,
      prompt_version: undefined,
      weight_config_hash: undefined,
      include_scene: true,
      sort: "desc",
    })
  }

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
          <Icon as={FiFilter} boxSize={5} />
          <Heading size="sm">Filters</Heading>
        </HStack>
        <Button
          variant="ghost"
          size="sm"
          gap={2}
          onClick={resetFilters}
          isDisabled={availableBooks.length === 0}
        >
          <Icon as={FiRefreshCcw} />
          Reset
        </Button>
      </Flex>
      <SimpleGrid columns={{ base: 1, md: 3 }} gap={4}>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Book
          </Text>
          <NativeSelectRoot disabled={!availableBooks.length} w="full">
            <NativeSelectField
              value={search.book_slug ?? ""}
              onChange={(event) => {
                const value = event.target.value || undefined
                handleChange({ book_slug: value })
              }}
            >
              <option value="">
                {availableBooks.length ? "Select a book" : "No books"}
              </option>
              {availableBooks.map((slug) => (
                <option key={slug} value={slug}>
                  {slug}
                </option>
              ))}
            </NativeSelectField>
            <NativeSelectIndicator />
          </NativeSelectRoot>
        </Box>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Limit
          </Text>
          <Input
            type="number"
            min={1}
            max={100}
            value={search.limit}
            onChange={(event) => {
              const raw = event.target.value
              if (!raw) {
                handleChange({ limit: undefined })
                return
              }
              const parsed = Number(raw)
              if (!Number.isNaN(parsed)) {
                handleChange({ limit: parsed })
              }
            }}
          />
        </Box>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Sort
          </Text>
          <NativeSelectRoot w="full">
            <NativeSelectField
              value={search.sort}
              onChange={(event) =>
                handleChange({
                  sort: event.target.value as SceneRankingSearch["sort"],
                })
              }
            >
              <option value="desc">Highest overall first</option>
              <option value="asc">Lowest overall first</option>
            </NativeSelectField>
            <NativeSelectIndicator />
          </NativeSelectRoot>
        </Box>
      </SimpleGrid>
      <SimpleGrid columns={{ base: 1, md: 3 }} gap={4}>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Model Name
          </Text>
          <Input
            placeholder="gemini-2.5-flash"
            value={search.model_name ?? ""}
            onChange={(event) => {
              const value = event.target.value
              handleChange({ model_name: value || undefined })
            }}
          />
        </Box>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Prompt Version
          </Text>
          <Input
            placeholder="v1"
            value={search.prompt_version ?? ""}
            onChange={(event) => {
              const value = event.target.value
              handleChange({ prompt_version: value || undefined })
            }}
          />
        </Box>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            Weight Config Hash
          </Text>
          <Input
            placeholder="auto"
            value={search.weight_config_hash ?? ""}
            onChange={(event) => {
              const value = event.target.value
              handleChange({ weight_config_hash: value || undefined })
            }}
          />
        </Box>
      </SimpleGrid>
      <Box>
        <Text fontSize="xs" textTransform="uppercase" mb={1} color="fg.subtle">
          Include Scene Details
        </Text>
        <NativeSelectRoot w="full">
          <NativeSelectField
            value={includeScene ? "true" : "false"}
            onChange={(event) =>
              handleChange({ include_scene: event.target.value === "true" })
            }
          >
            <option value="true">Yes (show excerpt summaries)</option>
            <option value="false">No (ranking metadata only)</option>
          </NativeSelectField>
          <NativeSelectIndicator />
        </NativeSelectRoot>
      </Box>
      {isFetching && (
        <HStack gap={2} color="fg.muted">
          <Spinner size="sm" />
          <Text fontSize="xs">Updating filters…</Text>
        </HStack>
      )}
    </Stack>
  )
}

const ScoreGrid = ({ scores }: { scores: Record<string, number> }) => (
  <SimpleGrid columns={{ base: 1, sm: 2, md: 3 }} gap={3}>
    {Object.entries(scores).map(([key, value]) => (
      <Box key={key} borderWidth="1px" borderRadius="md" p={3} bg="bg.muted">
        <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
          {toTitleCase(key)}
        </Text>
        <Text fontWeight="bold" fontSize="lg">
          {value.toFixed(1)}
        </Text>
      </Box>
    ))}
  </SimpleGrid>
)

const RankingMetadata = ({ ranking }: { ranking: SceneRanking }) => (
  <SimpleGrid columns={{ base: 1, sm: 2, md: 3 }} gap={3}>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        Model
      </Text>
      <Text>
        {ranking.model_vendor} · {ranking.model_name}
      </Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        Prompt Version
      </Text>
      <Text>{ranking.prompt_version}</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        Weight Config
      </Text>
      <Text>{ranking.weight_config_hash}</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        LLM Request
      </Text>
      <Text>{ranking.llm_request_id ?? "—"}</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        Created
      </Text>
      <Text>{formatDateTime(ranking.created_at)}</Text>
    </Box>
    <Box>
      <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={1}>
        Execution Time
      </Text>
      <Text>
        {ranking.execution_time_ms !== null &&
        ranking.execution_time_ms !== undefined
          ? `${ranking.execution_time_ms} ms`
          : "—"}
      </Text>
    </Box>
  </SimpleGrid>
)

const SceneSummary = ({ ranking }: { ranking: SceneRanking }) => {
  const scene = ranking.scene
  if (!scene) {
    return null
  }

  return (
    <Stack gap={4}>
      <Heading size="sm">Scene Summary</Heading>
      <SimpleGrid columns={{ base: 1, sm: 2 }} gap={3}>
        <Box>
          <Text
            fontSize="xs"
            color="fg.subtle"
            textTransform="uppercase"
            mb={1}
          >
            Book
          </Text>
          <Text>{scene.book_slug}</Text>
        </Box>
        <Box>
          <Text
            fontSize="xs"
            color="fg.subtle"
            textTransform="uppercase"
            mb={1}
          >
            Chapter
          </Text>
          <Text>
            #{scene.chapter_number} · {scene.chapter_title}
          </Text>
        </Box>
        <Box>
          <Text
            fontSize="xs"
            color="fg.subtle"
            textTransform="uppercase"
            mb={1}
          >
            Scene Number
          </Text>
          <Text>{scene.scene_number}</Text>
        </Box>
        <Box>
          <Text
            fontSize="xs"
            color="fg.subtle"
            textTransform="uppercase"
            mb={1}
          >
            Location Marker
          </Text>
          <Text>{scene.location_marker}</Text>
        </Box>
        <Box>
          <Text
            fontSize="xs"
            color="fg.subtle"
            textTransform="uppercase"
            mb={1}
          >
            Refinement Decision
          </Text>
          <Text>{scene.refinement_decision ?? "—"}</Text>
        </Box>
      </SimpleGrid>
      <Box>
        <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={2}>
          Refined Excerpt
        </Text>
        <Box
          p={3}
          borderRadius="md"
          borderWidth="1px"
          bg="bg.muted"
          whiteSpace="pre-wrap"
          fontSize="sm"
        >
          {scene.refined ?? "—"}
        </Box>
      </Box>
      <Box>
        <Text fontSize="xs" color="fg.subtle" textTransform="uppercase" mb={2}>
          Raw Excerpt
        </Text>
        <Box
          p={3}
          borderRadius="md"
          borderWidth="1px"
          bg="bg.muted"
          whiteSpace="pre-wrap"
          fontSize="sm"
        >
          {scene.raw}
        </Box>
      </Box>
    </Stack>
  )
}

const SceneRankingItem = ({ ranking }: { ranking: SceneRanking }) => {
  const warnings = ranking.warnings ?? []
  const characterTags = ranking.character_tags ?? []
  const scenePreviewSource =
    ranking.scene?.refined ?? ranking.scene?.raw ?? ""
  const scenePreview = scenePreviewSource
    ? truncateText(scenePreviewSource.replace(/\s+/g, " ").trim(), 300)
    : undefined

  return (
    <AccordionItem
      value={ranking.id}
      borderRadius="lg"
      borderWidth="1px"
      mb={3}
      bg="bg.surface"
    >
      <AccordionItemTrigger _expanded={{ bg: "bg.subtle" }} px={4} py={4}>
        <Flex align="center" flex="1" gap={3} textAlign="left">
          <Box>
            <HStack gap={3} align="center" mb={1}>
              <Badge colorScheme="purple" borderRadius="full" px={2} py={0.5}>
                {ranking.overall_priority.toFixed(2)} overall
              </Badge>
              <Badge variant="outline" borderRadius="full" px={2} py={0.5}>
                {ranking.prompt_version}
              </Badge>
              {ranking.scene && (
                <Badge colorScheme="blue" borderRadius="full" px={2} py={0.5}>
                  Scene {ranking.scene.scene_number}
                </Badge>
              )}
            </HStack>
            <Text fontWeight="semibold">
              {ranking.scene?.chapter_title ?? "Ranking"}
            </Text>
            <Text fontSize="sm" color="fg.muted">
              {ranking.model_name} · {formatDateTime(ranking.created_at)}
            </Text>
            {scenePreview && (
              <Text fontSize="sm" color="fg.subtle" mt={2}>
                {scenePreview}
              </Text>
            )}
          </Box>
        </Flex>
        <AccordionItemIndicator />
      </AccordionItemTrigger>
      <AccordionItemContent px={4} pb={4}>
        <Stack gap={6} pt={2}>
          <Stack gap={2}>
            <Heading size="sm">Ranking Overview</Heading>
            <RankingMetadata ranking={ranking} />
          </Stack>
          <Stack gap={2}>
            <Heading size="sm">Score Breakdown</Heading>
            <ScoreGrid scores={ranking.scores} />
          </Stack>
          {ranking.justification && (
            <Box>
              <Heading size="sm" mb={2}>
                Justification
              </Heading>
              <Box
                borderWidth="1px"
                borderRadius="md"
                p={3}
                bg="bg.muted"
                whiteSpace="pre-wrap"
                fontSize="sm"
              >
                {ranking.justification}
              </Box>
            </Box>
          )}
          {warnings.length > 0 && (
            <Stack gap={2}>
              <Heading size="sm" display="flex" alignItems="center" gap={2}>
                <Icon as={FiAlertTriangle} /> Content Warnings
              </Heading>
              <HStack gap={2} wrap="wrap">
                {warnings.map((warning) => (
                  <TagRoot key={warning} colorScheme="red" variant="subtle">
                    <TagLabel>{warning}</TagLabel>
                  </TagRoot>
                ))}
              </HStack>
            </Stack>
          )}
          {characterTags.length > 0 && (
            <Stack gap={2}>
              <Heading size="sm">Character Tags</Heading>
              <HStack gap={2} wrap="wrap">
                {characterTags.map((tag) => (
                  <TagRoot key={tag} colorScheme="green" variant="subtle">
                    <TagLabel>{tag}</TagLabel>
                  </TagRoot>
                ))}
              </HStack>
            </Stack>
          )}
          <SceneSummary ranking={ranking} />
        </Stack>
      </AccordionItemContent>
    </AccordionItem>
  )
}

function SceneRankingsPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })

  const updateSearch = useCallback<FilterUpdater>(
    (updates) => {
      navigate({
        search: (prev: SceneRankingSearch) => {
          const result: Record<string, unknown> = { ...prev, ...updates }
          for (const [key, value] of Object.entries(result)) {
            if (typeof value === "string") {
              const trimmed = value.trim()
              if (trimmed.length === 0) {
                delete result[key]
              } else {
                result[key] = trimmed
              }
            } else if (value === undefined || value === null) {
              delete result[key]
            }
          }
          return result as SceneRankingSearch
        },
      })
    },
    [navigate],
  )

  const filtersQuery = useQuery({
    queryKey: ["scene-extractions", "filters"],
    queryFn: SceneExtractionService.filters,
  })

  useEffect(() => {
    const books = filtersQuery.data?.books ?? []
    if (!search.book_slug && books.length) {
      const defaultBook = books[0]
      if (defaultBook) {
        updateSearch({ book_slug: defaultBook })
      }
    }
  }, [filtersQuery.data, search.book_slug, updateSearch])

  const cleanSearch = useMemo<SceneRankingTopParams | undefined>(() => {
    if (!search.book_slug) {
      return undefined
    }
    const includeScene = search.include_scene ?? true
    return {
      book_slug: search.book_slug,
      limit: search.limit,
      model_name: search.model_name,
      prompt_version: search.prompt_version,
      weight_config_hash: search.weight_config_hash,
      include_scene: includeScene,
    }
  }, [search])

  const listQuery = useQuery({
    queryKey: ["scene-rankings", "top", cleanSearch],
    queryFn: () =>
      SceneRankingService.listTop(cleanSearch as SceneRankingTopParams),
    enabled: Boolean(cleanSearch),
    placeholderData: (prev) => prev,
  })

  const rankings = useMemo(() => {
    const data = listQuery.data?.data ?? []
    if (search.sort === "asc") {
      return [...data].sort((a, b) => a.overall_priority - b.overall_priority)
    }
    return [...data].sort((a, b) => b.overall_priority - a.overall_priority)
  }, [listQuery.data, search.sort])

  const totalMeta = listQuery.data?.meta?.count
  const total = typeof totalMeta === "number" ? totalMeta : rankings.length
  const appliedBook = cleanSearch?.book_slug

  return (
    <Container maxW="7xl" py={8}>
      <Stack gap={6}>
        <Flex align="center" justify="space-between">
          <HStack gap={3}>
            <Icon as={FiTrendingUp} boxSize={6} />
            <Heading size="lg">Scene Rankings</Heading>
          </HStack>
          <Badge
            colorScheme="purple"
            fontSize="sm"
            px={3}
            py={1}
            borderRadius="full"
          >
            {total ?? rankings.length} results
          </Badge>
        </Flex>
        <SceneRankingFilters
          search={search}
          onChange={updateSearch}
          availableBooks={filtersQuery.data?.books ?? []}
          isFetching={filtersQuery.isFetching}
        />
        <Separator />
        {!appliedBook ? (
          <Flex align="center" justify="center" minH="200px">
            <Spinner size="lg" />
          </Flex>
        ) : listQuery.isError ? (
          <AlertRoot status="error" borderRadius="md">
            <AlertIndicator />
            <AlertContent>
              {listQuery.error instanceof Error
                ? listQuery.error.message
                : "Unable to load scene rankings right now."}
            </AlertContent>
          </AlertRoot>
        ) : listQuery.isLoading ? (
          <Flex align="center" justify="center" minH="200px">
            <Spinner size="lg" />
          </Flex>
        ) : rankings.length === 0 ? (
          <VStack gap={4} py={16} borderWidth="1px" borderRadius="lg">
            <Icon as={FiSearch} boxSize={8} color="fg.muted" />
            <Text fontSize="lg" fontWeight="medium">
              No rankings found for these filters
            </Text>
            <Text color="fg.muted" fontSize="sm" textAlign="center">
              Try adjusting the filters or selecting a different book.
            </Text>
          </VStack>
        ) : (
          <AccordionRoot
            multiple
            defaultValue={rankings.length ? [rankings[0].id] : []}
          >
            {rankings.map((ranking) => (
              <SceneRankingItem key={ranking.id} ranking={ranking} />
            ))}
          </AccordionRoot>
        )}
      </Stack>
    </Container>
  )
}

export default SceneRankingsPage
