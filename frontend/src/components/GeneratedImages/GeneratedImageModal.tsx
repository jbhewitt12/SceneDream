import {
  Badge,
  Box,
  HStack,
  IconButton,
  Image,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { FiChevronLeft, FiChevronRight } from "react-icons/fi"

import { GeneratedImageApi } from "@/api/generatedImages"
import { OpenAPI } from "@/client"
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogHeader,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog"

type GeneratedImageModalProps = {
  isOpen: boolean
  onClose: () => void
  imageId: string | null
  sceneId: string | null
  allImages?: Array<{ id: string; scene_extraction_id: string }>
  onNavigate?: (imageId: string, sceneId: string) => void
}

const GeneratedImageModal = ({
  isOpen,
  onClose,
  imageId,
  sceneId,
  allImages = [],
  onNavigate,
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

  const handlePreviousVariant = () => {
    if (sceneImages.length === 0 || !imageId || !onNavigate) return
    const currentIndex = sceneImages.findIndex((img) => img.id === imageId)
    if (currentIndex === -1) return
    const newIndex = (currentIndex - 1 + sceneImages.length) % sceneImages.length
    const newImage = sceneImages[newIndex]
    if (newImage) {
      onNavigate(newImage.id, newImage.scene_extraction_id)
    }
  }

  const handleNextVariant = () => {
    if (sceneImages.length === 0 || !imageId || !onNavigate) return
    const currentIndex = sceneImages.findIndex((img) => img.id === imageId)
    if (currentIndex === -1) return
    const newIndex = (currentIndex + 1) % sceneImages.length
    const newImage = sceneImages[newIndex]
    if (newImage) {
      onNavigate(newImage.id, newImage.scene_extraction_id)
    }
  }

  const handlePreviousScene = () => {
    if (allImages.length === 0 || !imageId || !onNavigate) return
    const currentGalleryIndex = allImages.findIndex((img) => img.id === imageId)
    if (currentGalleryIndex === -1) return

    // Find the previous image that has a different scene_extraction_id
    for (let i = currentGalleryIndex - 1; i >= 0; i--) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
    // If no previous scene found, wrap to the last scene
    for (let i = allImages.length - 1; i > currentGalleryIndex; i--) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
  }

  const handleNextScene = () => {
    if (allImages.length === 0 || !imageId || !onNavigate) return
    const currentGalleryIndex = allImages.findIndex((img) => img.id === imageId)
    if (currentGalleryIndex === -1) return

    // Find the next image that has a different scene_extraction_id
    for (let i = currentGalleryIndex + 1; i < allImages.length; i++) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
    // If no next scene found, wrap to the first scene
    for (let i = 0; i < currentGalleryIndex; i++) {
      if (allImages[i].scene_extraction_id !== sceneId) {
        onNavigate(allImages[i].id, allImages[i].scene_extraction_id)
        return
      }
    }
  }

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
  }, [isOpen, imageId, sceneId, sceneImages, allImages, onNavigate])

  const fullPath = currentImage
    ? `${OpenAPI.BASE}/${currentImage.image.storage_path}/${currentImage.image.file_name}`
    : ""
  const hasMultipleImages = sceneImages.length > 1
  const currentIndex = imageId ? sceneImages.findIndex((img) => img.id === imageId) : -1

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
            {hasMultipleImages && currentIndex !== -1 && ` · ${currentIndex + 1} of ${sceneImages.length}`}
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
            <Box flex="1" display="flex" justifyContent="center" alignItems="center">
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
                    <Badge colorScheme="purple">{currentImage.image.quality}</Badge>
                    <Badge colorScheme="blue">{currentImage.image.style}</Badge>
                    <Badge colorScheme="gray">
                      Variant #{currentImage.image.variant_index + 1}
                    </Badge>
                  </HStack>
                  <Text fontSize="xs" color="fg.muted">
                    {currentImage.image.provider} · {currentImage.image.model}
                  </Text>
                </Box>

                {/* Prompt text */}
                {currentImage.prompt && (
                  <Box>
                    <Text fontWeight="bold" fontSize="sm" mb={2}>
                      Prompt
                    </Text>
                    {currentImage.prompt.style_tags &&
                      currentImage.prompt.style_tags.length > 0 && (
                        <HStack gap={2} wrap="wrap" mb={2}>
                          {currentImage.prompt.style_tags.map((tag) => (
                            <Badge key={tag} colorScheme="purple" variant="subtle">
                              {tag}
                            </Badge>
                          ))}
                        </HStack>
                      )}
                    <Text
                      fontSize="sm"
                      whiteSpace="pre-wrap"
                      fontFamily="mono"
                      color="fg.muted"
                    >
                      {currentImage.prompt.prompt_text}
                    </Text>
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
      </DialogContent>
    </DialogRoot>
  )
}

export default GeneratedImageModal
