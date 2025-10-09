import {
  Box,
  Button,
  Container,
  Flex,
  Heading,
  HStack,
  Icon,
  Input,
  NativeSelectField,
  NativeSelectIndicator,
  NativeSelectRoot,
  SimpleGrid,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useState } from "react"
import { FiFilter, FiRefreshCcw } from "react-icons/fi"
import { z } from "zod"

import { GeneratedImageApi } from "@/api/generatedImages"
import {
  type SceneExtractionFilterOptions,
  SceneExtractionService,
} from "@/api/sceneExtractions"
import {
  GeneratedImageCard,
  GeneratedImageModal,
} from "@/components/GeneratedImages"

const generatedImagesSearchSchema = z.object({
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
  provider: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  model: z
    .string()
    .trim()
    .min(1)
    .optional()
    .or(z.literal("").transform(() => undefined))
    .catch(undefined),
  page: z.coerce.number().int().min(1).catch(1),
  page_size: z.coerce.number().int().min(1).max(48).catch(24),
})

type GeneratedImagesSearch = z.infer<typeof generatedImagesSearchSchema>

type FilterUpdater = (updates: Partial<GeneratedImagesSearch>) => void

const GeneratedImagesFilters = ({
  search,
  onChange,
  options,
  isFetching,
}: {
  search: GeneratedImagesSearch
  onChange: FilterUpdater
  options: SceneExtractionFilterOptions | undefined
  isFetching: boolean
}) => {
  const books = options?.books ?? []
  const chapters = search.book_slug
    ? options?.chapters_by_book?.[search.book_slug] ?? []
    : []

  const disabled = !books.length

  const handleChange = (updates: Partial<GeneratedImagesSearch>) => {
    onChange({
      ...updates,
      page: 1,
    })
  }

  const resetFilters = () => {
    handleChange({
      chapter_number: undefined,
      provider: undefined,
      model: undefined,
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
      <SimpleGrid columns={{ base: 1, md: 4 }} gap={4}>
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
              <option value="">Select book</option>
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
            Provider
          </Text>
          <Input
            placeholder="e.g. openai"
            value={search.provider ?? ""}
            onChange={(event) =>
              handleChange({
                provider: event.target.value.trim() || undefined,
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
            placeholder="e.g. dall-e-3"
            value={search.model ?? ""}
            onChange={(event) =>
              handleChange({
                model: event.target.value.trim() || undefined,
              })
            }
            disabled={disabled}
          />
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}

const useGeneratedImagesData = (search: GeneratedImagesSearch) => {
  const queryEnabled = Boolean(search.book_slug)

  const query = useQuery({
    queryKey: ["generated-images", "list", search],
    queryFn: () =>
      GeneratedImageApi.list({
        book: search.book_slug!,
        chapter: search.chapter_number,
        provider: search.provider,
        model: search.model,
        limit: search.page_size,
        offset: (search.page - 1) * search.page_size,
      }),
    enabled: queryEnabled,
    placeholderData: (previousData) => previousData,
  })

  return query
}

export const Route = createFileRoute("/_layout/generated-images")({
  component: GeneratedImagesGalleryPage,
  validateSearch: (search) => generatedImagesSearchSchema.parse(search),
})

function GeneratedImagesGalleryPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null)
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const filtersQuery = useQuery({
    queryKey: ["scene-extractions", "filters"],
    queryFn: () => SceneExtractionService.filters(),
  })

  useEffect(() => {
    if (!search.book_slug && filtersQuery.data?.books?.length) {
      navigate({
        search: (prev) => ({
          ...prev,
          book_slug: filtersQuery.data?.books?.[0],
        }),
      })
    }
  }, [filtersQuery.data?.books, navigate, search.book_slug])

  const handleSearchUpdate = useCallback(
    (updates: Partial<GeneratedImagesSearch>) => {
      navigate({
        search: (prev) => ({
          ...prev,
          ...updates,
        }),
      })
    },
    [navigate],
  )

  const imagesQuery = useGeneratedImagesData(search)
  const images = imagesQuery.data?.data ?? []

  const pageSize = search.page_size
  const hasNextPage = images.length === pageSize
  const hasPrevPage = search.page > 1

  const handleImageClick = (imageId: string, sceneId: string) => {
    setSelectedImageId(imageId)
    setSelectedSceneId(sceneId)
    setIsModalOpen(true)
  }

  const handleModalClose = () => {
    setIsModalOpen(false)
    setSelectedImageId(null)
    setSelectedSceneId(null)
  }

  const handleNextPage = () => {
    handleSearchUpdate({ page: search.page + 1 })
  }

  const handlePrevPage = () => {
    handleSearchUpdate({ page: search.page - 1 })
  }

  return (
    <Container maxW="full" py={4} display="flex" flexDirection="column" gap={4}>
      <Flex align="center" justify="space-between">
        <Heading
          size="lg"
          bgGradient="linear(to-r, ui.main, #7f5af0)"
          bgClip="text"
        >
          Generated Images Gallery
        </Heading>
      </Flex>

      <Box position="sticky" top={0} zIndex={1} bg="bg.canvas">
        <GeneratedImagesFilters
          search={search}
          onChange={handleSearchUpdate}
          options={filtersQuery.data}
          isFetching={filtersQuery.isFetching}
        />
      </Box>

      {images.length === 0 && !imagesQuery.isLoading ? (
        <Box textAlign="center" py={10}>
          {search.book_slug ? (
            <Text>No generated images found for this selection.</Text>
          ) : (
            <Text>Select a book to browse generated images.</Text>
          )}
        </Box>
      ) : (
        <>
          <SimpleGrid columns={{ base: 1, sm: 2, md: 3, lg: 4, xl: 6 }} gap={4}>
            {images.map((image) => (
              <GeneratedImageCard
                key={image.id}
                image={image}
                onClick={() =>
                  handleImageClick(image.id, image.scene_extraction_id)
                }
              />
            ))}
          </SimpleGrid>

          {/* Pagination */}
          <Flex justify="center" align="center" gap={4} mt={4}>
            <Button
              onClick={handlePrevPage}
              disabled={!hasPrevPage || imagesQuery.isLoading}
              size="sm"
            >
              Previous
            </Button>
            <Text fontSize="sm">
              Page {search.page}
              {images.length === pageSize && "+"}
            </Text>
            <Button
              onClick={handleNextPage}
              disabled={!hasNextPage || imagesQuery.isLoading}
              size="sm"
            >
              Next
            </Button>
          </Flex>
        </>
      )}

      {/* Modal */}
      <GeneratedImageModal
        isOpen={isModalOpen}
        onClose={handleModalClose}
        imageId={selectedImageId}
        sceneId={selectedSceneId}
      />
    </Container>
  )
}
