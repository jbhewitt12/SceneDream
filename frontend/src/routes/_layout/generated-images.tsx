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
  SimpleGrid,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react"
import {
  type InfiniteData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useRef, useState } from "react"
import { FiFilter, FiRefreshCcw } from "react-icons/fi"
import { z } from "zod"

import {
  GeneratedImageApi,
  type GeneratedImageListResponse,
  type GeneratedImageRead,
  type GeneratedImageWithContext,
  updateImageApproval,
} from "@/api/generatedImages"
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
  approval: z
    .preprocess((value) => {
      if (value === undefined || value === "") return undefined
      if (value === true || value === "true" || value === "approved") {
        return true
      }
      if (value === false || value === "false" || value === "rejected") {
        return false
      }
      if (value === null || value === "null" || value === "pending") {
        return null
      }
      return value
    }, z.boolean().or(z.null()).optional())
    .catch(undefined),
  page_size: z.coerce.number().int().min(1).max(48).catch(24),
})

type GeneratedImagesSearch = z.infer<typeof generatedImagesSearchSchema>

type FilterUpdater = (updates: Partial<GeneratedImagesSearch>) => void

type ApprovalMutationVariables = {
  imageId: string
  approved: boolean | null
}

type ApprovalMutationContext = {
  previousList?: InfiniteData<GeneratedImageListResponse>
  previousModal?: GeneratedImageWithContext
  previousScene?: GeneratedImageListResponse
  sceneQueryKey?: readonly ["generated-images", "scene", string]
}

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
    onChange(updates)
  }

  const resetFilters = () => {
    handleChange({
      chapter_number: undefined,
      provider: undefined,
      model: undefined,
      approval: undefined,
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
      <SimpleGrid columns={{ base: 1, md: 5 }} gap={4}>
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
              <option value="">All books</option>
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
        <Stack spacing={1}>
          <Text textTransform="uppercase" fontSize="xs" color="fg.subtle">
            Approval
          </Text>
          <NativeSelectRoot disabled={disabled} w="full">
            <NativeSelectField
              value={
                search.approval === true
                  ? "approved"
                  : search.approval === false
                    ? "rejected"
                    : search.approval === null
                      ? "pending"
                      : ""
              }
              onChange={(event) => {
                const val = event.target.value
                handleChange({
                  approval:
                    val === "approved"
                      ? true
                      : val === "rejected"
                        ? false
                        : val === "pending"
                          ? null
                          : undefined,
                })
              }}
            >
              <option value="">All images</option>
              <option value="approved">Approved only</option>
              <option value="rejected">Rejected only</option>
              <option value="pending">Pending only</option>
            </NativeSelectField>
            <NativeSelectIndicator />
          </NativeSelectRoot>
        </Stack>
      </SimpleGrid>
    </Stack>
  )
}

const useGeneratedImagesData = (search: GeneratedImagesSearch) => {
  const queryEnabled = true
  const queryKey = ["generated-images", "list", search] as const

  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam = 0 }) =>
      GeneratedImageApi.list({
        book: search.book_slug,
        chapter: search.chapter_number,
        provider: search.provider,
        model: search.model,
        approval: search.approval,
        limit: search.page_size,
        offset: pageParam,
      }),
    enabled: queryEnabled,
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      // If the last page has fewer items than the page size, there are no more pages
      if (lastPage.data.length < search.page_size) {
        return undefined
      }
      // Calculate the next offset
      return allPages.length * search.page_size
    },
  })

  return { query, queryKey }
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
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()

  const filtersQuery = useQuery({
    queryKey: ["scene-extractions", "filters"],
    queryFn: () => SceneExtractionService.filters(),
  })

  const handleSearchUpdate = useCallback(
    (updates: Partial<GeneratedImagesSearch>) => {
      navigate({
        search: (prev: GeneratedImagesSearch) => ({
          ...prev,
          ...updates,
        }),
      })
    },
    [navigate],
  )

  const { query: imagesQuery, queryKey: listQueryKey } =
    useGeneratedImagesData(search)

  const approvalMutation = useMutation<
    GeneratedImageRead,
    Error,
    ApprovalMutationVariables,
    ApprovalMutationContext
  >({
    mutationFn: ({ imageId, approved }) =>
      updateImageApproval(imageId, approved),
    onMutate: async ({ imageId, approved }) => {
      await queryClient.cancelQueries({ queryKey: listQueryKey })

      const previousList =
        queryClient.getQueryData<InfiniteData<GeneratedImageListResponse>>(
          listQueryKey,
        )
      const modalQueryKey = ["generated-image", imageId] as const
      const previousModal =
        queryClient.getQueryData<GeneratedImageWithContext>(modalQueryKey)

      const sceneIdFromList = previousList?.pages
        .flatMap((page) => page.data)
        .find((img) => img.id === imageId)?.scene_extraction_id
      const sceneIdFromModal = previousModal?.image.scene_extraction_id
      const sceneId = sceneIdFromList ?? sceneIdFromModal ?? null
      const sceneQueryKey = sceneId
        ? (["generated-images", "scene", sceneId] as const)
        : undefined
      const previousScene = sceneQueryKey
        ? queryClient.getQueryData<GeneratedImageListResponse>(sceneQueryKey)
        : undefined

      const optimisticTimestamp = new Date().toISOString()

      queryClient.setQueryData(
        listQueryKey,
        (old: InfiniteData<GeneratedImageListResponse> | undefined) => {
          if (!old) return old
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((img) =>
                img.id === imageId
                  ? {
                      ...img,
                      user_approved: approved,
                      approval_updated_at: optimisticTimestamp,
                    }
                  : img,
              ),
            })),
          }
        },
      )

      if (previousModal) {
        queryClient.setQueryData(modalQueryKey, {
          ...previousModal,
          image: {
            ...previousModal.image,
            user_approved: approved,
            approval_updated_at: optimisticTimestamp,
          },
        })
      }

      if (sceneQueryKey) {
        queryClient.setQueryData<GeneratedImageListResponse | undefined>(
          sceneQueryKey,
          (old) => {
            if (!old) return old
            return {
              ...old,
              data: old.data.map((img) =>
                img.id === imageId
                  ? {
                      ...img,
                      user_approved: approved,
                      approval_updated_at: optimisticTimestamp,
                    }
                  : img,
              ),
            }
          },
        )
      }

      return {
        previousList,
        previousModal,
        previousScene,
        sceneQueryKey,
      }
    },
    onError: (_error, variables, context) => {
      if (context?.previousList) {
        queryClient.setQueryData(listQueryKey, context.previousList)
      }
      if (context?.previousModal) {
        queryClient.setQueryData(
          ["generated-image", variables.imageId],
          context.previousModal,
        )
      }
      if (context?.sceneQueryKey && context.previousScene) {
        queryClient.setQueryData(context.sceneQueryKey, context.previousScene)
      }
    },
    onSuccess: (data, variables, context) => {
      queryClient.setQueryData(
        listQueryKey,
        (old: InfiniteData<GeneratedImageListResponse> | undefined) => {
          if (!old) return old
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              data: page.data.map((img) => (img.id === data.id ? data : img)),
            })),
          }
        },
      )

      queryClient.setQueryData(
        ["generated-image", variables.imageId],
        (old: GeneratedImageWithContext | undefined) => {
          if (!old) return old
          return {
            ...old,
            image: {
              ...old.image,
              user_approved: data.user_approved,
              approval_updated_at: data.approval_updated_at,
            },
          }
        },
      )

      if (context?.sceneQueryKey) {
        queryClient.setQueryData<GeneratedImageListResponse | undefined>(
          context.sceneQueryKey,
          (old) => {
            if (!old) return old
            return {
              ...old,
              data: old.data.map((img) => (img.id === data.id ? data : img)),
            }
          },
        )
      }
    },
    onSettled: (_data, _error, variables, context) => {
      queryClient.invalidateQueries({ queryKey: listQueryKey })
      queryClient.invalidateQueries({
        queryKey: ["generated-image", variables.imageId],
      })
      if (context?.sceneQueryKey) {
        queryClient.invalidateQueries({ queryKey: context.sceneQueryKey })
      }
    },
  })

  const handleApprovalChange = useCallback(
    (imageId: string, approved: boolean | null) => {
      approvalMutation.mutate({ imageId, approved })
    },
    [approvalMutation],
  )

  // Flatten all pages into a single array
  const images = (imagesQuery.data?.pages ?? [])
    .flatMap((page) => page.data)
    .filter((image) => !image.error)
    .filter((image) => {
      if (search.approval === undefined) return true
      if (search.approval === null) return image.user_approved === null
      return image.user_approved === search.approval
    })

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

  const handleNavigate = (imageId: string, sceneId: string) => {
    setSelectedImageId(imageId)
    setSelectedSceneId(sceneId)
  }

  // Intersection Observer for infinite scroll
  useEffect(() => {
    if (!loadMoreRef.current) return
    if (!imagesQuery.hasNextPage) return
    if (imagesQuery.isFetchingNextPage) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && imagesQuery.hasNextPage) {
          imagesQuery.fetchNextPage()
        }
      },
      { threshold: 0.1 },
    )

    observer.observe(loadMoreRef.current)

    return () => observer.disconnect()
  }, [
    imagesQuery.hasNextPage,
    imagesQuery.isFetchingNextPage,
    imagesQuery.fetchNextPage,
  ])

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
          <SimpleGrid columns={{ base: 1, sm: 2, md: 3 }} gap={4}>
            {images.map((image) => (
              <GeneratedImageCard
                key={image.id}
                image={image}
                onClick={() =>
                  handleImageClick(image.id, image.scene_extraction_id)
                }
                onApprovalChange={handleApprovalChange}
              />
            ))}
          </SimpleGrid>

          {/* Infinite scroll loading indicator */}
          <Box ref={loadMoreRef} py={8} textAlign="center">
            {imagesQuery.isFetchingNextPage ? (
              <Flex justify="center" align="center" gap={2}>
                <Spinner size="sm" />
                <Text fontSize="sm" color="fg.subtle">
                  Loading more images...
                </Text>
              </Flex>
            ) : imagesQuery.hasNextPage ? (
              <Text fontSize="sm" color="fg.subtle">
                Scroll for more
              </Text>
            ) : images.length > 0 ? (
              <Text fontSize="sm" color="fg.subtle">
                No more images
              </Text>
            ) : null}
          </Box>
        </>
      )}

      {/* Modal */}
      <GeneratedImageModal
        isOpen={isModalOpen}
        onClose={handleModalClose}
        imageId={selectedImageId}
        sceneId={selectedSceneId}
        allImages={images.map((img) => ({
          id: img.id,
          scene_extraction_id: img.scene_extraction_id,
        }))}
        onNavigate={handleNavigate}
        onApprovalChange={handleApprovalChange}
      />
    </Container>
  )
}
