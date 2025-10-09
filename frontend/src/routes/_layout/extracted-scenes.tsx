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
  Text,
  VStack,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { type ChangeEvent, useMemo } from "react"
import { FiFilter, FiRefreshCcw, FiSearch } from "react-icons/fi"
import { z } from "zod"

import {
  type SceneExtraction,
  type SceneExtractionFilterOptions,
  type SceneExtractionListParams,
  SceneExtractionService,
} from "@/api/sceneExtractions"
import { InputGroup } from "@/components/ui/input-group"
import {
  PaginationItems,
  PaginationNextTrigger,
  PaginationPrevTrigger,
  PaginationRoot,
} from "@/components/ui/pagination"

const extractedScenesSearchSchema = z.object({
  page: z.coerce.number().int().min(1).catch(1),
  page_size: z.coerce.number().int().min(1).max(100).catch(20),
  book_slug: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .or(z.undefined())
    .catch(undefined),
  chapter_number: z.coerce
    .number()
    .int()
    .min(0)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  decision: z.string().trim().min(1).catch("keep"),
  has_refined: z
    .enum(["true", "false"])
    .transform((value) => value === "true")
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  search: z
    .string()
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  start_date: z
    .string()
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  end_date: z
    .string()
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  order: z.enum(["asc", "desc"]).catch("desc"),
})

type ExtractedScenesSearch = z.infer<typeof extractedScenesSearchSchema>

type FilterUpdater = (updates: Partial<ExtractedScenesSearch>) => void

export const Route = createFileRoute("/_layout/extracted-scenes")({
  component: ExtractedScenesPage,
  validateSearch: (search) => extractedScenesSearchSchema.parse(search),
})

const formatDateTime = (value: string | null) => {
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

const SceneExtractionFilters = ({
  search,
  onChange,
  options,
  isFetching,
}: {
  search: ExtractedScenesSearch
  onChange: FilterUpdater
  options: SceneExtractionFilterOptions | undefined
  isFetching: boolean
}) => {
  const bookOptions = options?.books ?? []
  const chaptersForBook = useMemo(() => {
    if (!search.book_slug) {
      return []
    }
    return options?.chapters_by_book?.[search.book_slug] ?? []
  }, [options?.chapters_by_book, search.book_slug])

  const decisionOptions = options?.refinement_decisions ?? []
  const decisionValue = decisionOptions.length
    ? search.decision ?? "keep"
    : "all"
  const hasRefinedValue = search.has_refined ?? undefined

  const handleChange = (patch: Partial<ExtractedScenesSearch>) => {
    onChange({
      ...patch,
      page: 1,
    })
  }

  const resetFilters = () => {
    onChange({
      book_slug: undefined,
      chapter_number: undefined,
      decision: "keep",
      has_refined: undefined,
      search: undefined,
      start_date: undefined,
      end_date: undefined,
      page: 1,
    })
  }

  return (
    <Stack
      gap={4}
      p={4}
      borderWidth="1px"
      borderRadius="lg"
      bg="rgba(255,255,255,0.04)"
      backdropFilter="blur(8px) saturate(140%)"
      shadow="md"
    >
      <Flex align="center" justify="space-between">
        <HStack gap={2}>
          <Icon as={FiFilter} boxSize={5} />
          <Heading size="sm">Filters</Heading>
        </HStack>
        <Button variant="ghost" size="sm" gap={2} onClick={resetFilters}>
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
          <NativeSelectRoot disabled={!bookOptions.length} w="full">
            <NativeSelectField
              value={search.book_slug ?? ""}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                const value = event.target.value || undefined
                handleChange({
                  book_slug: value,
                  chapter_number: undefined,
                })
              }}
            >
              <option value="">
                {bookOptions.length ? "All books" : "No books"}
              </option>
              {bookOptions.map((slug) => (
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
            Chapter
          </Text>
          <NativeSelectRoot disabled={!chaptersForBook.length} w="full">
            <NativeSelectField
              value={search.chapter_number?.toString() ?? ""}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                const value = event.target.value
                handleChange({
                  chapter_number: value ? Number(value) : undefined,
                })
              }}
            >
              <option value="">
                {search.book_slug ? "All chapters" : "Select a book first"}
              </option>
              {chaptersForBook.map((chapter) => (
                <option key={chapter} value={chapter}>
                  Chapter {chapter}
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
            Decision
          </Text>
          <NativeSelectRoot disabled={!decisionOptions.length} w="full">
            <NativeSelectField
              value={decisionValue}
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                const value = event.target.value
                handleChange({ decision: value })
              }}
            >
              <option value="all">
                {decisionOptions.length ? "All decisions" : "No decisions yet"}
              </option>
              {decisionOptions.map((decision) => (
                <option key={decision} value={decision}>
                  {decision}
                </option>
              ))}
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
            Refinement
          </Text>
          <NativeSelectRoot w="full">
            <NativeSelectField
              value={
                hasRefinedValue === undefined
                  ? ""
                  : hasRefinedValue
                    ? "true"
                    : "false"
              }
              onChange={(event: ChangeEvent<HTMLSelectElement>) => {
                const value = event.target.value
                handleChange({
                  has_refined: value ? value === "true" : undefined,
                })
              }}
            >
              <option value="">All scenes</option>
              <option value="true">With refinement</option>
              <option value="false">Without refinement</option>
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
            Start Date
          </Text>
          <Input
            type="date"
            value={search.start_date ?? ""}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const value = event.target.value || undefined
              handleChange({ start_date: value })
            }}
            max={search.end_date ?? undefined}
          />
        </Box>
        <Box>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            mb={1}
            color="fg.subtle"
          >
            End Date
          </Text>
          <Input
            type="date"
            value={search.end_date ?? ""}
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const value = event.target.value || undefined
              handleChange({ end_date: value })
            }}
            min={search.start_date ?? undefined}
          />
        </Box>
      </SimpleGrid>
      <InputGroup
        startElement={<FiSearch color="var(--chakra-colors-fg-muted)" />}
        startElementProps={{ pointerEvents: "none" }}
      >
        <Input
          placeholder="Search excerpts, chapter titles, markers..."
          value={search.search ?? ""}
          onChange={(event: ChangeEvent<HTMLInputElement>) => {
            const value = event.target.value
            handleChange({ search: value || undefined })
          }}
        />
      </InputGroup>
      {options?.date_range && (
        <Text fontSize="xs" color="fg.muted">
          Showing data captured between{" "}
          {formatDateTime(options.date_range.earliest)} and{" "}
          {formatDateTime(options.date_range.latest)}
        </Text>
      )}
      {isFetching && (
        <HStack gap={2} color="fg.muted">
          <Spinner size="sm" />
          <Text fontSize="xs">Updating filters…</Text>
        </HStack>
      )}
    </Stack>
  )
}

const formatMetric = (value: number | null | undefined) => {
  if (value === null || value === undefined) {
    return "—"
  }
  return value.toString()
}

const metadataPairs = (scene: SceneExtraction) => {
  const refinedStatus = scene.refined ? "Refined" : "Raw only"
  return [
    { label: "Book", value: scene.book_slug },
    {
      label: "Chapter",
      value: `#${scene.chapter_number} · ${scene.chapter_title}`,
    },
    { label: "Scene", value: `#${scene.scene_number}` },
    { label: "Location Marker", value: scene.location_marker },
    { label: "Chunk", value: `#${scene.chunk_index}` },
    {
      label: "Paragraph Span",
      value: `${scene.chunk_paragraph_start} → ${scene.chunk_paragraph_end}`,
    },
    { label: "Extracted At", value: formatDateTime(scene.extracted_at) },
    { label: "Refined At", value: formatDateTime(scene.refined_at) },
    { label: "Extraction Model", value: scene.extraction_model ?? "—" },
    {
      label: "Extraction Temp",
      value:
        scene.extraction_temperature !== null &&
        scene.extraction_temperature !== undefined
          ? scene.extraction_temperature.toFixed(2)
          : "—",
    },
    { label: "Refinement Model", value: scene.refinement_model ?? "—" },
    {
      label: "Refinement Temp",
      value:
        scene.refinement_temperature !== null &&
        scene.refinement_temperature !== undefined
          ? scene.refinement_temperature.toFixed(2)
          : "—",
    },
    { label: "Raw Words", value: formatMetric(scene.raw_word_count) },
    { label: "Raw Characters", value: formatMetric(scene.raw_char_count) },
    { label: "Refined Words", value: formatMetric(scene.refined_word_count) },
    {
      label: "Refined Characters",
      value: formatMetric(scene.refined_char_count),
    },
    { label: "Signature", value: scene.raw_signature ?? "—" },
    {
      label: "Refinement Decision",
      value: scene.refinement_decision ?? refinedStatus,
    },
  ]
}

const SceneExtractionItem = ({ scene }: { scene: SceneExtraction }) => {
  const refined = Boolean(scene.refined)
  return (
    <AccordionItem
      value={String(scene.id)}
      borderRadius="lg"
      borderWidth="1px"
      mb={3}
    >
      <AccordionItemTrigger _expanded={{ bg: "bg.subtle" }}>
        <Flex align="center" flex="1" gap={3} textAlign="left">
          <Box>
            <Text fontWeight="semibold">
              {scene.chapter_title}
              <Text as="span" fontWeight="normal" color="fg.muted" ml={2}>
                Scene {scene.scene_number} · Chapter {scene.chapter_number}
              </Text>
            </Text>
            <Flex gap={2} mt={1} flexWrap="wrap">
              <Badge
                colorScheme={refined ? "green" : "purple"}
                fontSize="xs"
                px={2}
                py={0.5}
                borderRadius="full"
              >
                {refined ? "Refined" : "Raw"}
              </Badge>
              {scene.refinement_decision && (
                <Badge
                  fontSize="xs"
                  px={2}
                  py={0.5}
                  borderRadius="full"
                  colorScheme="blue"
                >
                  {scene.refinement_decision}
                </Badge>
              )}
              <Badge
                fontSize="xs"
                px={2}
                py={0.5}
                variant="outline"
                borderRadius="full"
              >
                {scene.book_slug}
              </Badge>
              <Badge
                fontSize="xs"
                px={2}
                py={0.5}
                variant="subtle"
                borderRadius="full"
              >
                {formatDateTime(scene.extracted_at)}
              </Badge>
            </Flex>
          </Box>
        </Flex>
        <AccordionItemIndicator />
      </AccordionItemTrigger>
      <AccordionItemContent>
        <Stack gap={6} pt={2}>
          <Box>
            <Text
              fontSize="sm"
              fontWeight="bold"
              textTransform="uppercase"
              mb={2}
            >
              Raw Excerpt
            </Text>
            <Box
              p={3}
              borderRadius="md"
              borderWidth="1px"
              bg="bg.muted"
              whiteSpace="pre-wrap"
              fontFamily="mono"
              fontSize="sm"
            >
              {scene.raw}
            </Box>
          </Box>
          {scene.refined && (
            <Box>
              <Text
                fontSize="sm"
                fontWeight="bold"
                textTransform="uppercase"
                mb={2}
              >
                Refined Excerpt
              </Text>
              <Box
                p={3}
                borderRadius="md"
                borderWidth="1px"
                bg="bg.muted"
                whiteSpace="pre-wrap"
                fontFamily="mono"
                fontSize="sm"
              >
                {scene.refined}
              </Box>
              {scene.refinement_rationale && (
                <Text mt={2} fontSize="sm" color="fg.muted">
                  Rationale: {scene.refinement_rationale}
                </Text>
              )}
            </Box>
          )}
          <Box>
            <Text
              fontSize="sm"
              fontWeight="bold"
              textTransform="uppercase"
              mb={2}
            >
              Metadata
            </Text>
            <SimpleGrid columns={{ base: 1, md: 2, xl: 3 }} gap={3}>
              {metadataPairs(scene).map(({ label, value }) => (
                <Box key={label} borderWidth="1px" borderRadius="md" p={3}>
                  <Text
                    fontSize="xs"
                    color="fg.muted"
                    textTransform="uppercase"
                  >
                    {label}
                  </Text>
                  <Text fontSize="sm" mt={1}>
                    {value || "—"}
                  </Text>
                </Box>
              ))}
            </SimpleGrid>
          </Box>
          {scene.props && (
            <Box>
              <Text
                fontSize="sm"
                fontWeight="bold"
                textTransform="uppercase"
                mb={2}
              >
                Additional Properties
              </Text>
              <Box
                p={3}
                borderRadius="md"
                borderWidth="1px"
                bg="bg.muted"
                whiteSpace="pre-wrap"
                fontFamily="mono"
                fontSize="sm"
              >
                {JSON.stringify(scene.props, null, 2)}
              </Box>
            </Box>
          )}
        </Stack>
      </AccordionItemContent>
    </AccordionItem>
  )
}

function ExtractedScenesPage() {
  const navigate = useNavigate({ from: Route.fullPath })
  const search = Route.useSearch()

  const cleanSearch = useMemo(() => {
    const toIsoString = (value?: string) => {
      if (!value) {
        return undefined
      }
      const date = new Date(value)
      if (Number.isNaN(date.getTime())) {
        return undefined
      }
      return date.toISOString()
    }

    const sanitized: SceneExtractionListParams = {
      page: search.page,
      page_size: search.page_size,
      order: search.order,
      book_slug: search.book_slug,
      chapter_number: search.chapter_number,
      decision: search.decision === "all" ? undefined : search.decision,
      has_refined: search.has_refined,
      search: search.search,
      start_date: toIsoString(search.start_date ?? undefined),
      end_date: toIsoString(search.end_date ?? undefined),
    }
    return sanitized
  }, [search])

  const listQuery = useQuery({
    queryKey: ["scene-extractions", cleanSearch],
    queryFn: () => SceneExtractionService.list(cleanSearch),
    placeholderData: (prev) => prev,
  })

  const filtersQuery = useQuery({
    queryKey: ["scene-extractions", "filters"],
    queryFn: SceneExtractionService.filters,
  })

  const updateSearch: FilterUpdater = (updates) => {
    navigate({
      search: (prev: ExtractedScenesSearch) => {
        const next = { ...prev, ...updates } as ExtractedScenesSearch
        if (updates.page === undefined) {
          next.page = updates.page ?? prev.page ?? 1
        }
        for (const [key, value] of Object.entries(next)) {
          if (
            value === undefined ||
            value === null ||
            (typeof value === "string" && value.trim() === "")
          ) {
            delete next[key as keyof typeof next]
          }
        }
        return next
      },
    })
  }

  const setPage = (page: number) => updateSearch({ page })

  const scenes = listQuery.data?.data ?? []
  const total = listQuery.data?.total ?? 0
  const pageSize = listQuery.data?.page_size ?? search.page_size

  return (
    <Container maxW="7xl" py={8}>
      <Stack gap={6}>
        <Flex align="center" justify="space-between">
          <Heading
            size="lg"
            bgGradient="linear(to-r, ui.main, #7f5af0)"
            bgClip="text"
          >
            Extracted Scenes
          </Heading>
          <Badge
            colorScheme="purple"
            fontSize="sm"
            px={3}
            py={1}
            borderRadius="full"
          >
            {total} total
          </Badge>
        </Flex>
        <SceneExtractionFilters
          search={search}
          onChange={updateSearch}
          options={filtersQuery.data}
          isFetching={filtersQuery.isFetching}
        />
        <Separator />
        <Stack gap={4}>
          {listQuery.isError ? (
            <AlertRoot status="error" borderRadius="md">
              <AlertIndicator />
              <AlertContent>
                {listQuery.error instanceof Error
                  ? listQuery.error.message
                  : "Unable to load scenes right now."}
              </AlertContent>
            </AlertRoot>
          ) : listQuery.isLoading ? (
            <Flex align="center" justify="center" minH="200px">
              <Spinner size="lg" />
            </Flex>
          ) : scenes.length === 0 ? (
            <VStack gap={4} py={16} borderWidth="1px" borderRadius="lg">
              <Icon as={FiSearch} boxSize={8} color="fg.muted" />
              <Text fontSize="lg" fontWeight="medium">
                No scenes found for these filters
              </Text>
              <Text color="fg.muted" fontSize="sm">
                Try adjusting your search or clearing the filters.
              </Text>
            </VStack>
          ) : (
            <AccordionRoot
              multiple
              defaultValue={scenes.length ? [String(scenes[0].id)] : []}
            >
              {scenes.map((scene) => (
                <SceneExtractionItem key={scene.id} scene={scene} />
              ))}
            </AccordionRoot>
          )}
          {total > pageSize && (
            <Flex justify="flex-end">
              <PaginationRoot
                count={total}
                pageSize={pageSize}
                page={search.page}
                onPageChange={({ page }) => setPage(page)}
              >
                <Flex align="center" gap={2}>
                  <PaginationPrevTrigger />
                  <PaginationItems />
                  <PaginationNextTrigger />
                </Flex>
              </PaginationRoot>
            </Flex>
          )}
        </Stack>
      </Stack>
    </Container>
  )
}

export default ExtractedScenesPage
