import {
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
  Stack,
  Text,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback } from "react"
import { FiFilter, FiRefreshCcw } from "react-icons/fi"
import { z } from "zod"

import { ImagePromptApi } from "@/api/imagePrompts"
import {
  type SceneExtractionFilterOptions,
  SceneExtractionService,
} from "@/api/sceneExtractions"
// Removed InputGroup for selects; using NativeSelect components instead
import { PromptList } from "@/components/Prompts"

const promptGallerySearchSchema = z.object({
  book_slug: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  chapter_number: z.coerce
    .number()
    .int()
    .min(0)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
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
  style_tag: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  page: z.coerce.number().int().min(1).catch(1),
  page_size: z.coerce.number().int().min(1).max(48).catch(24),
  include_scene: z
    .enum(["true", "false"])
    .transform((value) => value === "true")
    .catch(true),
})

type PromptGallerySearch = z.infer<typeof promptGallerySearchSchema>

type FilterUpdater = (updates: Partial<PromptGallerySearch>) => void

const PromptGalleryFilters = ({
  search,
  onChange,
  options,
  isFetching,
}: {
  search: PromptGallerySearch
  onChange: FilterUpdater
  options: SceneExtractionFilterOptions | undefined
  isFetching: boolean
}) => {
  const books = options?.books ?? []
  const chapters = search.book_slug
    ? options?.chapters_by_book?.[search.book_slug] ?? []
    : []

  const disabled = !books.length

  const handleChange = (updates: Partial<PromptGallerySearch>) => {
    onChange({
      ...updates,
      page: 1,
    })
  }

  const resetFilters = () => {
    handleChange({
      chapter_number: undefined,
      model_name: undefined,
      prompt_version: undefined,
      style_tag: undefined,
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
          <Icon as={FiFilter} />
          <Heading size="sm">Filters</Heading>
        </HStack>
        <Button size="sm" variant="ghost" gap={2} onClick={resetFilters}>
          <Icon as={FiRefreshCcw} />
          Reset
        </Button>
      </Flex>
      <SimpleGrid columns={{ base: 1, md: 3 }} gap={4}>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Book
          </Text>
          <NativeSelectRoot disabled={disabled || isFetching} w="full">
            <NativeSelectField
              value={search.book_slug ?? ""}
              onChange={(event) =>
                handleChange({
                  book_slug: event.target.value || undefined,
                  chapter_number: undefined,
                })
              }
            >
              <option value="">All Books</option>
              {books.map((book) => (
                <option key={book} value={book}>
                  {book}
                </option>
              ))}
            </NativeSelectField>
            <NativeSelectIndicator />
          </NativeSelectRoot>
        </Stack>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Chapter
          </Text>
          <NativeSelectRoot disabled={!chapters.length} w="full">
            <NativeSelectField
              value={search.chapter_number?.toString() ?? ""}
              onChange={(event) =>
                handleChange({
                  chapter_number: event.target.value
                    ? Number.parseInt(event.target.value, 10)
                    : undefined,
                })
              }
            >
              <option value="">All chapters</option>
              {chapters.map((chapter) => (
                <option key={chapter} value={chapter}>
                  Chapter {chapter}
                </option>
              ))}
            </NativeSelectField>
            <NativeSelectIndicator />
          </NativeSelectRoot>
        </Stack>
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Style tag
          </Text>
          <Input
            placeholder="e.g. cinematic"
            value={search.style_tag ?? ""}
            onChange={(event) =>
              handleChange({
                style_tag: event.target.value.trim() || undefined,
              })
            }
            disabled={disabled}
          />
        </Stack>
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
            disabled={disabled}
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
            disabled={disabled}
          />
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}

const usePromptGalleryData = (search: PromptGallerySearch) => {
  const query = useQuery({
    queryKey: ["image-prompts", "list", search],
    queryFn: () =>
      ImagePromptApi.list({
        bookSlug: search.book_slug ?? undefined,
        chapterNumber: search.chapter_number ?? undefined,
        modelName: search.model_name ?? undefined,
        promptVersion: search.prompt_version ?? undefined,
        styleTag: search.style_tag ?? undefined,
        page: search.page,
        pageSize: search.page_size,
        includeScene: search.include_scene,
      }),
    placeholderData: (previousData) => previousData,
    keepPreviousData: true,
  })

  return query
}

export const Route = createFileRoute("/_layout/prompt-gallery")({
  component: PromptGalleryPage,
  validateSearch: (search) => promptGallerySearchSchema.parse(search),
})

function PromptGalleryPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })

  const filtersQuery = useQuery({
    queryKey: ["scene-extractions", "filters"],
    queryFn: () => SceneExtractionService.filters(),
  })

  const handleSearchUpdate = useCallback(
    (updates: Partial<PromptGallerySearch>) => {
      navigate({
        search: (prev) => ({
          ...prev,
          ...updates,
        }),
      })
    },
    [navigate],
  )

  const promptQuery = usePromptGalleryData(search)
  const prompts = promptQuery.data?.data ?? []

  const pageSize = search.page_size
  const hasNextPage = prompts.length === pageSize

  return (
    <Container maxW="full" py={4} display="flex" flexDirection="column" gap={4}>
      <Flex align="center" justify="space-between">
        <Heading
          size="lg"
          bgGradient="linear(to-r, ui.main, #7f5af0)"
          bgClip="text"
        >
          Prompt Gallery
        </Heading>
      </Flex>
      <Box position="sticky" top={0} zIndex={1} bg="bg.canvas">
        <PromptGalleryFilters
          search={search}
          onChange={handleSearchUpdate}
          options={filtersQuery.data}
          isFetching={filtersQuery.isFetching}
        />
      </Box>
      <Separator />
      <PromptList
        prompts={prompts}
        isLoading={promptQuery.isLoading && !promptQuery.isPlaceholderData}
        pagination={{
          page: search.page,
          pageSize,
          hasNextPage,
          onPageChange: (page) => handleSearchUpdate({ page }),
        }}
        height="calc(100vh - 320px)"
        emptyState={<Text>No prompts yet for this selection.</Text>}
      />
    </Container>
  )
}
