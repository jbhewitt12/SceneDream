import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  IconButton,
  Image,
  Input,
  Separator,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
} from "@chakra-ui/react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react"
import {
  FiChevronLeft,
  FiChevronRight,
  FiCrop,
  FiEdit3,
  FiExternalLink,
  FiRefreshCw,
  FiShare2,
  FiThumbsDown,
  FiThumbsUp,
} from "react-icons/fi"

import {
  GeneratedImageApi,
  cropImage,
  getPostingStatus,
} from "@/api/generatedImages"
import { updatePromptMetadata } from "@/api/imagePrompts"
import {
  CropModal,
  MetadataRegenerationModal,
} from "@/components/GeneratedImages"
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogHeader,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog"
import useCustomToast from "@/hooks/useCustomToast"
import { buildGeneratedImageUrl } from "./url"

type GeneratedImageModalProps = {
  isOpen: boolean
  onClose: () => void
  imageId: string | null
  allImages?: Array<{ id: string; scene_extraction_id: string }>
  onNavigate?: (imageId: string) => void
  onApprovalChange?: (imageId: string, approved: boolean | null) => void
  onCustomRemix?: (imageId: string, customPromptText: string) => Promise<void>
  onQueueForPosting?: (imageId: string) => Promise<void>
}

type SidebarSectionProps = {
  eyebrow: string
  title?: string
  description?: string
  action?: ReactNode
  children: ReactNode
}

type DetailItemProps = {
  label: string
  value: ReactNode
}

const sectionCardStyles = {
  borderWidth: "1px",
  borderRadius: "xl",
  bg: "rgba(255,255,255,0.04)",
  backdropFilter: "blur(10px) saturate(140%)",
  boxShadow: "sm",
} as const

const SidebarSection = ({
  eyebrow,
  title,
  description,
  action,
  children,
}: SidebarSectionProps) => (
  <Box {...sectionCardStyles} px={4} py={4}>
    <Stack gap={4}>
      <Flex align="start" justify="space-between" gap={3}>
        <Stack gap={1}>
          <Text
            fontSize="xs"
            textTransform="uppercase"
            letterSpacing="0.12em"
            color="fg.subtle"
          >
            {eyebrow}
          </Text>
          {title ? (
            <Text fontSize="lg" fontWeight="semibold" lineHeight="1.2">
              {title}
            </Text>
          ) : null}
          {description ? (
            <Text fontSize="sm" color="fg.subtle">
              {description}
            </Text>
          ) : null}
        </Stack>
        {action}
      </Flex>
      {children}
    </Stack>
  </Box>
)

const DetailItem = ({ label, value }: DetailItemProps) => (
  <Stack gap={1}>
    <Text
      fontSize="xs"
      textTransform="uppercase"
      letterSpacing="0.12em"
      color="fg.subtle"
    >
      {label}
    </Text>
    <Text fontSize="sm" fontWeight="medium">
      {value}
    </Text>
  </Stack>
)

const GeneratedImageModal = ({
  isOpen,
  onClose,
  imageId,
  allImages = [],
  onNavigate,
  onApprovalChange,
  onCustomRemix,
  onQueueForPosting,
}: GeneratedImageModalProps) => {
  // Fetch the current image details with context
  const imageQuery = useQuery({
    queryKey: ["generated-image", imageId],
    queryFn: () => GeneratedImageApi.retrieve(imageId!, true, true),
    enabled: isOpen && imageId !== null,
  })

  // Fetch posting status
  const postingStatusQuery = useQuery({
    queryKey: ["posting-status", imageId],
    queryFn: () => getPostingStatus(imageId!),
    enabled: isOpen && imageId !== null,
  })

  const currentImage = imageQuery.data
  const postingStatus = postingStatusQuery.data
  const isLoading = imageQuery.isLoading || imageQuery.isFetching
  const promptText = currentImage?.prompt?.prompt_text ?? ""
  const promptTitle = currentImage?.prompt?.title?.trim() || ""
  const promptFlavour = currentImage?.prompt?.flavour_text?.trim() || ""

  const [editedPromptText, setEditedPromptText] = useState<string>("")
  const [isRemixing, setIsRemixing] = useState(false)
  const [isQueueing, setIsQueueing] = useState(false)
  const [isMetadataModalOpen, setIsMetadataModalOpen] = useState(false)
  const [isCropModalOpen, setIsCropModalOpen] = useState(false)
  const [imageCacheBuster, setImageCacheBuster] = useState<number>(0)
  const [editedTitle, setEditedTitle] = useState<string>("")
  const [editedFlavour, setEditedFlavour] = useState<string>("")
  const titleDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const flavourDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const metadataMutation = useMutation({
    mutationFn: ({
      promptId,
      title,
      flavourText,
    }: {
      promptId: string
      title?: string | null
      flavourText?: string | null
    }) =>
      updatePromptMetadata(promptId, {
        title,
        flavour_text: flavourText,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["generated-image", imageId] })
      queryClient.invalidateQueries({ queryKey: ["generated-images"] })
    },
  })

  useEffect(() => {
    setEditedPromptText(promptText)
  }, [promptText])

  useEffect(() => {
    setEditedTitle(promptTitle)
  }, [promptTitle])

  useEffect(() => {
    setEditedFlavour(promptFlavour)
  }, [promptFlavour])

  // Cleanup debounce timers on unmount
  useEffect(() => {
    return () => {
      if (titleDebounceRef.current) clearTimeout(titleDebounceRef.current)
      if (flavourDebounceRef.current) clearTimeout(flavourDebounceRef.current)
    }
  }, [])

  const handleTitleChange = useCallback(
    (value: string) => {
      setEditedTitle(value)
      if (titleDebounceRef.current) clearTimeout(titleDebounceRef.current)

      const promptId = currentImage?.prompt?.id
      if (!promptId) return

      titleDebounceRef.current = setTimeout(() => {
        const trimmed = value.trim()
        if (trimmed !== promptTitle) {
          metadataMutation.mutate({
            promptId,
            title: trimmed || null,
          })
        }
      }, 800)
    },
    [currentImage?.prompt?.id, promptTitle, metadataMutation],
  )

  const handleFlavourChange = useCallback(
    (value: string) => {
      setEditedFlavour(value)
      if (flavourDebounceRef.current) clearTimeout(flavourDebounceRef.current)

      const promptId = currentImage?.prompt?.id
      if (!promptId) return

      flavourDebounceRef.current = setTimeout(() => {
        const trimmed = value.trim()
        if (trimmed !== promptFlavour) {
          metadataMutation.mutate({
            promptId,
            flavourText: trimmed || null,
          })
        }
      }, 800)
    },
    [currentImage?.prompt?.id, promptFlavour, metadataMutation],
  )

  useEffect(() => {
    if (!isOpen) {
      setIsMetadataModalOpen(false)
      setIsCropModalOpen(false)
    }
  }, [isOpen])

  const handleNavigateByOffset = useCallback(
    (offset: number) => {
      if (allImages.length === 0 || !imageId || !onNavigate) return
      const currentIndex = allImages.findIndex((img) => img.id === imageId)
      if (currentIndex === -1) return
      const newIndex =
        (currentIndex + offset + allImages.length) % allImages.length
      const newImage = allImages[newIndex]
      if (newImage) {
        onNavigate(newImage.id)
      }
    },
    [allImages, imageId, onNavigate],
  )

  const handlePreviousImage = useCallback(
    () => handleNavigateByOffset(-1),
    [handleNavigateByOffset],
  )

  const handleNextImage = useCallback(
    () => handleNavigateByOffset(1),
    [handleNavigateByOffset],
  )

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      // Skip navigation if user is typing in an input or textarea
      const target = event.target as HTMLElement
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return
      }

      if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        event.preventDefault()
        handlePreviousImage()
      } else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        event.preventDefault()
        handleNextImage()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, handlePreviousImage, handleNextImage])

  const baseImageUrl = currentImage
    ? buildGeneratedImageUrl({
        id: currentImage.image.id,
        storagePath: currentImage.image.storage_path,
        fileName: currentImage.image.file_name,
      })
    : ""
  const fullPath = imageCacheBuster
    ? `${baseImageUrl}?t=${imageCacheBuster}`
    : baseImageUrl
  const hasMultipleImages = allImages.length > 1
  const currentIndex = imageId
    ? allImages.findIndex((img) => img.id === imageId)
    : -1
  const isEditedPromptInvalid =
    !editedPromptText.trim() || editedPromptText === promptText
  const approvalStateLabel =
    currentImage?.image.user_approved === true
      ? "Approved"
      : currentImage?.image.user_approved === false
        ? "Rejected"
        : null
  const approvalStatePalette =
    currentImage?.image.user_approved === true
      ? "green"
      : currentImage?.image.user_approved === false
        ? "red"
        : "gray"
  const isCustomRemixDisabled =
    isRemixing || isEditedPromptInvalid || !onCustomRemix

  const handleCustomRemix = async () => {
    if (!onCustomRemix || !currentImage?.image?.id) return
    if (isEditedPromptInvalid) return

    setIsRemixing(true)
    try {
      await onCustomRemix(currentImage.image.id, editedPromptText)
      setEditedPromptText(promptText)
    } catch (error) {
      console.error("Custom remix failed", error)
    } finally {
      setIsRemixing(false)
    }
  }

  const handleQueueForPosting = async () => {
    if (!onQueueForPosting || !currentImage?.image?.id) return

    setIsQueueing(true)
    try {
      await onQueueForPosting(currentImage.image.id)
      queryClient.invalidateQueries({ queryKey: ["posting-status", imageId] })
    } catch (error) {
      console.error("Queue for posting failed", error)
    } finally {
      setIsQueueing(false)
    }
  }

  const canQueueForPosting =
    currentImage?.image?.user_approved === true &&
    !postingStatus?.has_been_posted &&
    !postingStatus?.is_queued

  const handleCropComplete = useCallback(
    async (croppedBlob: Blob) => {
      if (!currentImage?.image?.id) return

      try {
        await cropImage(currentImage.image.id, croppedBlob)
        setIsCropModalOpen(false)
        setImageCacheBuster(Date.now())
        queryClient.invalidateQueries({
          queryKey: ["generated-image", imageId],
        })
        queryClient.invalidateQueries({ queryKey: ["generated-images"] })
        showSuccessToast("Image cropped successfully")
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Failed to crop image"
        showErrorToast(message)
        throw error
      }
    },
    [
      currentImage?.image?.id,
      imageId,
      queryClient,
      showErrorToast,
      showSuccessToast,
    ],
  )

  return (
    <DialogRoot
      open={isOpen}
      onOpenChange={(details) => {
        if (!details.open) {
          onClose()
        }
      }}
      size="full"
    >
      <DialogContent>
        <DialogCloseTrigger />
        <DialogHeader>
          <DialogTitle>
            {currentImage?.scene?.book_slug || "Generated Image"}
            {currentImage && ` · Chapter ${currentImage.image.chapter_number}`}
            {hasMultipleImages &&
              currentIndex !== -1 &&
              ` · ${currentIndex + 1} of ${allImages.length}`}
          </DialogTitle>
        </DialogHeader>
        <DialogBody>
          <HStack align="start" gap={6} h="full">
            {/* Left arrow */}
            {hasMultipleImages && (
              <IconButton
                aria-label="Previous image"
                onClick={handlePreviousImage}
                variant="ghost"
                size="lg"
                alignSelf="center"
                disabled={isLoading}
              >
                <FiChevronLeft />
              </IconButton>
            )}

            {/* Image */}
            <Box
              flex="1"
              display="flex"
              justifyContent="center"
              alignItems="center"
            >
              {currentImage &&
                (currentImage.image.file_deleted ? (
                  <Box
                    display="flex"
                    alignItems="center"
                    justifyContent="center"
                    w="full"
                    h="50vh"
                    bg="gray.200"
                    _dark={{ bg: "gray.700" }}
                    borderRadius="md"
                  >
                    <Text fontSize="lg" color="fg.muted">
                      File deleted
                    </Text>
                  </Box>
                ) : (
                  <Image
                    src={fullPath}
                    alt={`Generated image for chapter ${currentImage.image.chapter_number}`}
                    objectFit="contain"
                    maxH="70vh"
                    maxW="full"
                    loading="eager"
                  />
                ))}
            </Box>

            {/* Right arrow */}
            {hasMultipleImages && (
              <IconButton
                aria-label="Next image"
                onClick={handleNextImage}
                variant="ghost"
                size="lg"
                alignSelf="center"
                disabled={isLoading}
              >
                <FiChevronRight />
              </IconButton>
            )}

            {/* Context panel */}
            {currentImage && (
              <Stack
                gap={4}
                maxW="md"
                minW="xs"
                overflowY="auto"
                maxH="70vh"
                pr={2}
              >
                {(onApprovalChange || onQueueForPosting) && (
                  <SidebarSection eyebrow="Review and publishing">
                    <Stack gap={4}>
                      {onApprovalChange && (
                        <Box
                          borderWidth="1px"
                          borderRadius="lg"
                          borderColor="whiteAlpha.200"
                          bg="blackAlpha.200"
                          px={3}
                          py={3}
                        >
                          <Stack gap={3}>
                            <HStack justify="space-between" align="center">
                              <Text fontSize="sm" fontWeight="medium">
                                Approval
                              </Text>
                              {approvalStateLabel ? (
                                <Badge
                                  colorPalette={approvalStatePalette}
                                  variant="subtle"
                                >
                                  {approvalStateLabel}
                                </Badge>
                              ) : null}
                            </HStack>
                            <HStack gap={2} align="center">
                              <IconButton
                                aria-label="Approve image"
                                variant={
                                  currentImage.image.user_approved === true
                                    ? "solid"
                                    : "outline"
                                }
                                colorPalette={
                                  currentImage.image.user_approved === true
                                    ? "green"
                                    : "gray"
                                }
                                onClick={() =>
                                  onApprovalChange(
                                    currentImage.image.id,
                                    currentImage.image.user_approved === true
                                      ? null
                                      : true,
                                  )
                                }
                              >
                                <FiThumbsUp />
                              </IconButton>
                              <IconButton
                                aria-label="Reject image"
                                variant={
                                  currentImage.image.user_approved === false
                                    ? "solid"
                                    : "outline"
                                }
                                colorPalette={
                                  currentImage.image.user_approved === false
                                    ? "red"
                                    : "gray"
                                }
                                onClick={() =>
                                  onApprovalChange(
                                    currentImage.image.id,
                                    currentImage.image.user_approved === false
                                      ? null
                                      : false,
                                  )
                                }
                              >
                                <FiThumbsDown />
                              </IconButton>
                            </HStack>
                          </Stack>
                        </Box>
                      )}

                      {onApprovalChange && onQueueForPosting && <Separator />}

                      {onQueueForPosting && (
                        <Stack gap={3}>
                          <HStack justify="space-between" align="center">
                            <Text fontSize="sm" fontWeight="medium">
                              Social media
                            </Text>
                            {canQueueForPosting && (
                              <Button
                                size="sm"
                                variant="outline"
                                colorPalette="blue"
                                loading={isQueueing}
                                loadingText="Queueing"
                                onClick={handleQueueForPosting}
                              >
                                <FiShare2 />
                                Queue for Posting
                              </Button>
                            )}
                          </HStack>
                          {postingStatus?.posts &&
                          postingStatus.posts.length > 0 ? (
                            <Stack gap={2}>
                              {postingStatus.posts.map((post) => (
                                <Box
                                  key={post.id}
                                  borderWidth="1px"
                                  borderRadius="lg"
                                  borderColor="whiteAlpha.200"
                                  bg="blackAlpha.200"
                                  px={3}
                                  py={3}
                                >
                                  <Stack gap={2}>
                                    <HStack
                                      justify="space-between"
                                      align="center"
                                    >
                                      <Badge
                                        colorPalette={
                                          post.status === "posted"
                                            ? "green"
                                            : post.status === "failed"
                                              ? "red"
                                              : "blue"
                                        }
                                      >
                                        {post.service_name}
                                      </Badge>
                                      <Text fontSize="xs" color="fg.muted">
                                        {post.status === "posted"
                                          ? "Posted"
                                          : post.status === "queued"
                                            ? "Queued"
                                            : "Failed"}
                                      </Text>
                                    </HStack>
                                    {post.error_message &&
                                    post.status === "failed" ? (
                                      <Text fontSize="xs" color="red.400">
                                        {post.error_message}
                                      </Text>
                                    ) : null}
                                    {post.external_url ? (
                                      <Button
                                        aria-label="Open social post"
                                        size="xs"
                                        variant="ghost"
                                        justifyContent="flex-start"
                                        asChild
                                      >
                                        <a
                                          href={post.external_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                        >
                                          <FiExternalLink />
                                          View post
                                        </a>
                                      </Button>
                                    ) : null}
                                  </Stack>
                                </Box>
                              ))}
                            </Stack>
                          ) : (
                            <Text fontSize="sm" color="fg.subtle">
                              {currentImage.image.user_approved !== true
                                ? "Approve this image first to unlock social sharing."
                                : "No social posts yet. Queue this image when you are ready to publish it."}
                            </Text>
                          )}
                        </Stack>
                      )}
                    </Stack>
                  </SidebarSection>
                )}

                {currentImage.prompt && (
                  <SidebarSection
                    eyebrow="Prompt body"
                    title="Edit and remix"
                    description="Adjust the actual prompt text, then trigger a fresh variation from your edited version."
                  >
                    <Stack gap={3}>
                      <Textarea
                        value={editedPromptText}
                        onChange={(event) =>
                          setEditedPromptText(event.target.value)
                        }
                        fontSize="sm"
                        fontFamily="mono"
                        color="fg.muted"
                        minH="220px"
                        resize="vertical"
                        disabled={isRemixing}
                        bg="blackAlpha.200"
                        borderColor="whiteAlpha.200"
                      />
                      <HStack
                        justify="space-between"
                        align="center"
                        wrap="wrap"
                      >
                        <Button
                          size="sm"
                          variant="outline"
                          colorPalette="purple"
                          loading={isRemixing}
                          loadingText="Remixing"
                          onClick={handleCustomRemix}
                          disabled={isCustomRemixDisabled}
                        >
                          <FiEdit3 />
                          Remix with Edits
                        </Button>
                      </HStack>
                    </Stack>
                  </SidebarSection>
                )}

                {currentImage.scene && (
                  <SidebarSection
                    eyebrow="Scene context"
                    title={`Scene ${currentImage.scene.scene_number}`}
                    description={`${currentImage.scene.chapter_title} · ${currentImage.scene.location_marker}`}
                  >
                    <Stack gap={4}>
                      <SimpleGrid columns={{ base: 1, sm: 2 }} gap={4}>
                        <DetailItem
                          label="Book"
                          value={currentImage.scene.book_slug}
                        />
                        <DetailItem
                          label="Chapter"
                          value={`#${currentImage.scene.chapter_number}`}
                        />
                      </SimpleGrid>
                      <Box
                        borderWidth="1px"
                        borderRadius="lg"
                        borderColor="whiteAlpha.200"
                        bg="blackAlpha.200"
                        px={3}
                        py={3}
                      >
                        <Text
                          fontSize="sm"
                          whiteSpace="pre-wrap"
                          color="fg.muted"
                        >
                          {currentImage.scene.refined || currentImage.scene.raw}
                        </Text>
                      </Box>
                    </Stack>
                  </SidebarSection>
                )}

                {currentImage.prompt && (
                  <SidebarSection
                    eyebrow="Prompt overview"
                    action={
                      <Button
                        size="xs"
                        variant="outline"
                        colorPalette="purple"
                        onClick={() => setIsMetadataModalOpen(true)}
                        disabled={!currentImage?.prompt?.id}
                        alignSelf="start"
                      >
                        <FiRefreshCw />
                        Regenerate
                      </Button>
                    }
                  >
                    <Stack gap={3}>
                      <Stack gap={1}>
                        <Text
                          fontSize="xs"
                          textTransform="uppercase"
                          letterSpacing="0.12em"
                          color="fg.subtle"
                        >
                          Title
                        </Text>
                        <Input
                          value={editedTitle}
                          onChange={(e) => handleTitleChange(e.target.value)}
                          placeholder="Title"
                          fontSize="lg"
                          fontWeight="semibold"
                          size="sm"
                          bg="blackAlpha.200"
                          borderColor="whiteAlpha.200"
                        />
                      </Stack>
                      <Stack gap={1}>
                        <Text
                          fontSize="xs"
                          textTransform="uppercase"
                          letterSpacing="0.12em"
                          color="fg.subtle"
                        >
                          Flavour text
                        </Text>
                        <Textarea
                          value={editedFlavour}
                          onChange={(e) => handleFlavourChange(e.target.value)}
                          placeholder="Description / flavour text"
                          fontSize="sm"
                          color="fg.subtle"
                          fontStyle="italic"
                          resize="none"
                          minH="88px"
                          bg="blackAlpha.200"
                          borderColor="whiteAlpha.200"
                        />
                      </Stack>
                      <HStack
                        justify="space-between"
                        align="center"
                        wrap="wrap"
                      >
                        {metadataMutation.isPending ? (
                          <Text fontSize="xs" color="fg.muted">
                            Saving copy changes...
                          </Text>
                        ) : (
                          <Box />
                        )}
                        <HStack gap={2} wrap="wrap">
                          {approvalStateLabel ? (
                            <Badge
                              colorPalette={approvalStatePalette}
                              variant="subtle"
                            >
                              {approvalStateLabel}
                            </Badge>
                          ) : null}
                          <Badge colorPalette="gray" variant="subtle">
                            Variant #{currentImage.image.variant_index + 1}
                          </Badge>
                        </HStack>
                      </HStack>
                      {currentImage.prompt.style_tags &&
                        currentImage.prompt.style_tags.length > 0 && (
                          <>
                            <Separator />
                            <Stack gap={2}>
                              <Text
                                fontSize="xs"
                                textTransform="uppercase"
                                letterSpacing="0.12em"
                                color="fg.subtle"
                              >
                                Style tags
                              </Text>
                              <HStack gap={2} wrap="wrap">
                                {currentImage.prompt.style_tags.map((tag) => (
                                  <Badge
                                    key={tag}
                                    colorPalette="purple"
                                    variant="subtle"
                                  >
                                    {tag}
                                  </Badge>
                                ))}
                              </HStack>
                            </Stack>
                          </>
                        )}
                    </Stack>
                  </SidebarSection>
                )}

                <SidebarSection
                  eyebrow="Image details"
                  action={
                    <IconButton
                      aria-label="Crop image"
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsCropModalOpen(true)}
                      disabled={currentImage.image.file_deleted}
                    >
                      <FiCrop />
                    </IconButton>
                  }
                >
                  <Stack gap={4}>
                    <HStack gap={2} wrap="wrap">
                      <Badge>{currentImage.image.size}</Badge>
                      <Badge colorPalette="purple">
                        {currentImage.image.quality}
                      </Badge>
                      <Badge colorPalette="blue">
                        {currentImage.image.style}
                      </Badge>
                    </HStack>
                    <SimpleGrid columns={{ base: 1, sm: 2 }} gap={4}>
                      <DetailItem
                        label="Provider"
                        value={currentImage.image.provider}
                      />
                      <DetailItem
                        label="Model"
                        value={currentImage.image.model}
                      />
                      <DetailItem
                        label="Chapter"
                        value={`#${currentImage.image.chapter_number}`}
                      />
                      <DetailItem
                        label="Variant"
                        value={`#${currentImage.image.variant_index + 1}`}
                      />
                    </SimpleGrid>
                  </Stack>
                </SidebarSection>
              </Stack>
            )}
          </HStack>
        </DialogBody>
        <MetadataRegenerationModal
          isOpen={isMetadataModalOpen}
          onClose={() => setIsMetadataModalOpen(false)}
          promptId={currentImage?.prompt?.id ?? null}
          imageId={currentImage?.image?.id ?? null}
        />
        <CropModal
          isOpen={isCropModalOpen}
          onClose={() => setIsCropModalOpen(false)}
          imageSrc={baseImageUrl}
          onCropComplete={handleCropComplete}
        />
      </DialogContent>
    </DialogRoot>
  )
}

export default GeneratedImageModal
