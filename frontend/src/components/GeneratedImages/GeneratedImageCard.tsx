import { useState } from "react"

import {
  Badge,
  Box,
  HStack,
  IconButton,
  Image,
  Stack,
  Text,
} from "@chakra-ui/react"

import { FiShuffle, FiThumbsDown, FiThumbsUp } from "react-icons/fi"

import type { GeneratedImageRead } from "@/api/generatedImages"
import { buildGeneratedImageUrl } from "./url"

type GeneratedImageCardProps = {
  image: GeneratedImageRead
  onClick: () => void
  onApprovalChange?: (imageId: string, approved: boolean | null) => void
  onRemix?: (imageId: string) => Promise<void> | void
}

const GeneratedImageCard = ({
  image,
  onClick,
  onApprovalChange,
  onRemix,
}: GeneratedImageCardProps) => {
  const [isRemixing, setIsRemixing] = useState(false)
  const [remixCompleted, setRemixCompleted] = useState(false)

  const fullPath = buildGeneratedImageUrl({
    id: image.id,
    storagePath: image.storage_path,
    fileName: image.file_name,
  })
  const aspectRatioLabel = image.aspect_ratio || image.size
  const borderColor =
    image.user_approved === true
      ? "green.500"
      : image.user_approved === false
        ? "red.500"
        : "border"

  return (
    <Box
      borderWidth="1px"
      borderRadius="lg"
      overflow="hidden"
      bg="bg.surface"
      shadow="sm"
      cursor="pointer"
      onClick={onClick}
      transition="all 0.2s"
      borderColor={borderColor}
      _hover={{
        shadow: "md",
        transform: "translateY(-2px)",
      }}
      display="flex"
      flexDirection="column"
    >
      <Box
        position="relative"
        bg="gray.100"
        _dark={{ bg: "gray.800" }}
        aspectRatio={
          image.width && image.height ? image.width / image.height : 1
        }
      >
        <Image
          src={fullPath}
          alt={`Generated image for chapter ${image.chapter_number}, variant ${
            image.variant_index + 1
          }`}
          objectFit="cover"
          w="full"
          h="full"
          loading="lazy"
        />
        {image.error && (
          <Box
            position="absolute"
            top={0}
            left={0}
            right={0}
            bottom={0}
            bg="rgba(255, 0, 0, 0.1)"
            display="flex"
            alignItems="center"
            justifyContent="center"
          >
            <Badge colorScheme="red">Error</Badge>
          </Box>
        )}
      </Box>

      <Stack gap={2} p={3}>
        <HStack justify="space-between" wrap="wrap">
          <Text fontSize="xs" fontWeight="medium">
            Chapter {image.chapter_number}
          </Text>
          <Badge colorScheme="purple" variant="subtle">
            Variant #{image.variant_index + 1}
          </Badge>
        </HStack>

        <HStack gap={2} wrap="wrap" fontSize="2xs">
          <Badge colorScheme="gray" variant="outline">
            {aspectRatioLabel}
          </Badge>
          <Badge colorScheme="gray" variant="outline">
            {image.quality}
          </Badge>
          <Badge colorScheme="gray" variant="outline">
            {image.style}
          </Badge>
        </HStack>

        {(onRemix || onApprovalChange) && (
          <HStack gap={2} justify="center" pt={1}>
            {onRemix && (
              <IconButton
                aria-label="Remix image"
                size="sm"
                variant="outline"
                colorPalette="purple"
                isLoading={isRemixing}
                isDisabled={isRemixing || remixCompleted}
                title={
                  remixCompleted
                    ? "Remix already triggered"
                    : "Generate subtle variations of this image"
                }
                onClick={async (event) => {
                  event.stopPropagation()
                  if (!onRemix || isRemixing || remixCompleted) {
                    return
                  }

                  try {
                    setIsRemixing(true)
                    await Promise.resolve(onRemix(image.id))
                    setRemixCompleted(true)
                  } catch (error) {
                    setRemixCompleted(false)
                  } finally {
                    setIsRemixing(false)
                  }
                }}
              >
                <FiShuffle />
              </IconButton>
            )}

            {onApprovalChange && (
              <>
                <IconButton
                  aria-label="Approve image"
                  size="sm"
                  variant={image.user_approved === true ? "solid" : "ghost"}
                  colorPalette={image.user_approved === true ? "green" : "gray"}
                  onClick={(event) => {
                    event.stopPropagation()
                    onApprovalChange(
                      image.id,
                      image.user_approved === true ? null : true,
                    )
                  }}
                >
                  <FiThumbsUp />
                </IconButton>
                <IconButton
                  aria-label="Reject image"
                  size="sm"
                  variant={image.user_approved === false ? "solid" : "ghost"}
                  colorPalette={image.user_approved === false ? "red" : "gray"}
                  onClick={(event) => {
                    event.stopPropagation()
                    onApprovalChange(
                      image.id,
                      image.user_approved === false ? null : false,
                    )
                  }}
                >
                  <FiThumbsDown />
                </IconButton>
              </>
            )}
          </HStack>
        )}
      </Stack>
    </Box>
  )
}

export default GeneratedImageCard
