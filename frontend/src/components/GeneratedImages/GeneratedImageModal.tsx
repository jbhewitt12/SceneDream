import {
  Badge,
  Box,
  Button,
  HStack,
  IconButton,
  Image,
  Stack,
  Text,
  Textarea,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { useCallback, useEffect, useState } from "react"
import {
  FiChevronLeft,
  FiChevronRight,
  FiEdit3,
  FiRefreshCw,
  FiThumbsDown,
  FiThumbsUp,
} from "react-icons/fi"

import { GeneratedImageApi } from "@/api/generatedImages"
import { MetadataRegenerationModal } from "@/components/GeneratedImages"
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogHeader,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog"
import { buildGeneratedImageUrl } from "./url"

type GeneratedImageModalProps = {
  isOpen: boolean
  onClose: () => void
  imageId: string | null
  sceneId: string | null
  allImages?: Array<{ id: string; scene_extraction_id: string }>
  onNavigate?: (imageId: string, sceneId: string) => void
  onApprovalChange?: (imageId: string, approved: boolean | null) => void
  onCustomRemix?: (imageId: string, customPromptText: string) => Promise<void>
}

const GeneratedImageModal = ({
  isOpen,
  onClose,
  imageId,
  sceneId,
  allImages = [],
  onNavigate,
  onApprovalChange,
  onCustomRemix,
}: GeneratedImageModalProps) => {
  // Fetch the current image details with context
  const imageQuery = useQuery({
    queryKey: ["generated-image", imageId],
    queryFn: () => GeneratedImageApi.retrieve(imageId!, true, true),
    enabled: isOpen && imageId !== null,
  })

  // Fetch all images for the scene to enable carousel
  const sceneImagesQuery = useQuery({
    queryKey: ["generated-images", "scene", sceneId],
    queryFn: () =>
      GeneratedImageApi.listForScene({
        sceneId: sceneId!,
        limit: 100,
        newestFirst: false,
      }),
    enabled: isOpen && sceneId !== null,
  })

  const sceneImages = sceneImagesQuery.data?.data ?? []
  const currentImage = imageQuery.data
  const isLoading = imageQuery.isLoading || imageQuery.isFetching
  const promptText = currentImage?.prompt?.prompt_text ?? ""
  const promptTitle = currentImage?.prompt?.title?.trim() || ""
  const promptFlavour = currentImage?.prompt?.flavour_text?.trim() || ""

  const [editedPromptText, setEditedPromptText] = useState<string>("")
  const [isRemixing, setIsRemixing] = useState(false)
  const [isMetadataModalOpen, setIsMetadataModalOpen] = useState(false)

  useEffect(() => {
    setEditedPromptText(promptText)
  }, [promptText])

  useEffect(() => {
    if (!isOpen) {
      setIsMetadataModalOpen(false)
    }
  }, [isOpen])

  const handlePreviousVariant = useCallback(() => {
    if (sceneImages.length === 0 || !imageId || !onNavigate) return
    const currentIndex = sceneImages.findIndex((img) => img.id === imageId)
    if (currentIndex === -1) return
    const newIndex =
      (currentIndex - 1 + sceneImages.length) % sceneImages.length
    const newImage = sceneImages[newIndex]
    if (newImage) {
      onNavigate(newImage.id, newImage.scene_extraction_id)
    }
  }, [sceneImages, imageId, onNavigate])

  const handleNextVariant = useCallback(() => {
    if (sceneImages.length === 0 || !imageId || !onNavigate) return
    const currentIndex = sceneImages.findIndex((img) => img.id === imageId)
    if (currentIndex === -1) return
    const newIndex = (currentIndex + 1) % sceneImages.length
    const newImage = sceneImages[newIndex]
    if (newImage) {
      onNavigate(newImage.id, newImage.scene_extraction_id)
    }
  }, [sceneImages, imageId, onNavigate])

  const handlePreviousScene = useCallback(() => {
    if (allImages.length === 0 || !imageId || !onNavigate) return
    const currentGalleryIndex = allImages.findIndex((img) => img.id === imageId)
    if (currentGalleryIndex === -1) return

    for (let i = currentGalleryIndex - 1; i >= 0; i--) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
    for (let i = allImages.length - 1; i > currentGalleryIndex; i--) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
  }, [allImages, imageId, onNavigate, sceneId])

  const handleNextScene = useCallback(() => {
    if (allImages.length === 0 || !imageId || !onNavigate) return
    const currentGalleryIndex = allImages.findIndex((img) => img.id === imageId)
    if (currentGalleryIndex === -1) return

    for (let i = currentGalleryIndex + 1; i < allImages.length; i++) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
    for (let i = 0; i < currentGalleryIndex; i++) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
  }, [allImages, imageId, onNavigate, sceneId])

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault()
        handlePreviousVariant()
      } else if (event.key === "ArrowRight") {
        event.preventDefault()
        handleNextVariant()
      } else if (event.key === "ArrowUp") {
        event.preventDefault()
        handlePreviousScene()
      } else if (event.key === "ArrowDown") {
        event.preventDefault()
        handleNextScene()
      }
    }

    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [
    isOpen,
    handlePreviousVariant,
    handleNextVariant,
    handlePreviousScene,
    handleNextScene,
  ])

  const fullPath = currentImage
    ? buildGeneratedImageUrl({
        id: currentImage.image.id,
        storagePath: currentImage.image.storage_path,
        fileName: currentImage.image.file_name,
      })
    : ""
  const hasMultipleImages = sceneImages.length > 1
  const currentIndex = imageId
    ? sceneImages.findIndex((img) => img.id === imageId)
    : -1
  const isEditedPromptInvalid =
    !editedPromptText.trim() || editedPromptText === promptText
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
              ` · ${currentIndex + 1} of ${sceneImages.length}`}
          </DialogTitle>
        </DialogHeader>
        <DialogBody>
          <HStack align="start" gap={6} h="full">
            {/* Left arrow */}
            {hasMultipleImages && (
              <IconButton
                aria-label="Previous image"
                onClick={handlePreviousVariant}
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
              {currentImage && (
                <Image
                  src={fullPath}
                  alt={`Generated image for chapter ${currentImage.image.chapter_number}`}
                  objectFit="contain"
                  maxH="70vh"
                  maxW="full"
                  loading="eager"
                />
              )}
            </Box>

            {/* Right arrow */}
            {hasMultipleImages && (
              <IconButton
                aria-label="Next image"
                onClick={handleNextVariant}
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
                {/* Image metadata */}
                <Box>
                  <Text fontWeight="bold" fontSize="sm" mb={2}>
                    Image Details
                  </Text>
                  <HStack gap={2} wrap="wrap" mb={2}>
                    <Badge>{currentImage.image.size}</Badge>
                    <Badge colorScheme="purple">
                      {currentImage.image.quality}
                    </Badge>
                    <Badge colorScheme="blue">{currentImage.image.style}</Badge>
                    <Badge colorScheme="gray">
                      Variant #{currentImage.image.variant_index + 1}
                    </Badge>
                  </HStack>
                  <Text fontSize="xs" color="fg.muted">
                    {currentImage.image.provider} · {currentImage.image.model}
                  </Text>
                </Box>

                {/* Approval controls */}
                {onApprovalChange && (
                  <Box>
                    <Text fontWeight="bold" fontSize="sm" mb={2}>
                      Approval
                    </Text>
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
                      {currentImage.image.user_approved != null && (
                        <Text fontSize="xs" color="fg.muted" ml={2}>
                          {currentImage.image.user_approved
                            ? "Approved"
                            : "Rejected"}
                        </Text>
                      )}
                    </HStack>
                  </Box>
                )}

                {/* Prompt text */}
                {currentImage.prompt && (
                  <Box>
                    <Text fontWeight="bold" fontSize="sm" mb={2}>
                      Prompt
                    </Text>
                    {(promptTitle || promptFlavour) && (
                      <Stack gap={1} mb={promptFlavour ? 3 : 2}>
                        {promptTitle && (
                          <Text fontSize="md" fontWeight="semibold">
                            {promptTitle}
                          </Text>
                        )}
                        {promptFlavour && (
                          <Text
                            fontSize="sm"
                            color="fg.subtle"
                            fontStyle="italic"
                          >
                            {promptFlavour}
                          </Text>
                        )}
                      </Stack>
                    )}
                    <HStack
                      justify="space-between"
                      align="center"
                      mt={promptTitle || promptFlavour ? 0 : 1}
                      mb={2}
                    >
                      <Text fontSize="xs" color="fg.muted">
                        {promptTitle || promptFlavour
                          ? "Generated metadata"
                          : "No metadata yet"}
                      </Text>
                      <Button
                        size="xs"
                        variant="ghost"
                        colorPalette="purple"
                        onClick={() => setIsMetadataModalOpen(true)}
                        disabled={!currentImage?.prompt?.id}
                      >
                        <HStack gap={1} align="center">
                          <FiRefreshCw aria-hidden="true" />
                          <Text as="span">Regenerate</Text>
                        </HStack>
                      </Button>
                    </HStack>
                    {currentImage.prompt.style_tags &&
                      currentImage.prompt.style_tags.length > 0 && (
                        <HStack gap={2} wrap="wrap" mb={2}>
                          {currentImage.prompt.style_tags.map((tag) => (
                            <Badge
                              key={tag}
                              colorScheme="purple"
                              variant="subtle"
                            >
                              {tag}
                            </Badge>
                          ))}
                        </HStack>
                      )}
                    <Textarea
                      value={editedPromptText}
                      onChange={(event) =>
                        setEditedPromptText(event.target.value)
                      }
                      fontSize="sm"
                      fontFamily="mono"
                      color="fg.muted"
                      minH="200px"
                      resize="vertical"
                      isDisabled={isRemixing}
                    />
                    <HStack justify="flex-end" mt={2}>
                      <Button
                        size="sm"
                        variant="outline"
                        colorPalette="purple"
                        leftIcon={<FiEdit3 />}
                        isLoading={isRemixing}
                        loadingText="Remixing"
                        onClick={handleCustomRemix}
                        isDisabled={isCustomRemixDisabled}
                      >
                        Remix with Edits
                      </Button>
                    </HStack>
                  </Box>
                )}

                {/* Scene text */}
                {currentImage.scene && (
                  <Box>
                    <Text fontWeight="bold" fontSize="sm" mb={2}>
                      Scene {currentImage.scene.scene_number}
                    </Text>
                    <Text fontSize="xs" color="fg.subtle" mb={1}>
                      {currentImage.scene.chapter_title} ·{" "}
                      {currentImage.scene.location_marker}
                    </Text>
                    <Text fontSize="sm" whiteSpace="pre-wrap" color="fg.muted">
                      {currentImage.scene.refined || currentImage.scene.raw}
                    </Text>
                  </Box>
                )}
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
      </DialogContent>
    </DialogRoot>
  )
}

export default GeneratedImageModal
