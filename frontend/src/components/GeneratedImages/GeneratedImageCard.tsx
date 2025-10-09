import {
  Badge,
  Box,
  HStack,
  Image,
  Stack,
  Text,
} from "@chakra-ui/react"

import type { GeneratedImageRead } from "@/api/generatedImages"
import { OpenAPI } from "@/client"

type GeneratedImageCardProps = {
  image: GeneratedImageRead
  onClick: () => void
}

const GeneratedImageCard = ({ image, onClick }: GeneratedImageCardProps) => {
  const fullPath = `${OpenAPI.BASE}/${image.storage_path}/${image.file_name}`
  const aspectRatioLabel = image.aspect_ratio || image.size

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
        aspectRatio={image.width && image.height ? image.width / image.height : 1}
      >
        <Image
          src={fullPath}
          alt={`Generated image for chapter ${image.chapter_number}, variant ${image.variant_index + 1}`}
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
      </Stack>
    </Box>
  )
}

export default GeneratedImageCard
