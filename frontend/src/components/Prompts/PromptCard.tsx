import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Icon,
  SimpleGrid,
  Stack,
  TagLabel,
  TagRoot,
  Text,
  useClipboard,
} from "@chakra-ui/react"
import { useMemo } from "react"
import { FiCopy, FiMaximize2 } from "react-icons/fi"

import type { ImagePrompt } from "@/api/imagePrompts"
import useCustomToast from "@/hooks/useCustomToast"

const DISPLAY_ATTRIBUTE_KEYS = [
  "composition",
  "camera",
  "lens",
  "lighting",
  "palette",
  "aspect_ratio",
  "references",
]

const formatAttributeValue = (value: unknown): string | null => {
  if (Array.isArray(value)) {
    const stringValues = value.filter((item) => typeof item === "string")
    return stringValues.length ? stringValues.join(", ") : null
  }

  if (typeof value === "string") {
    return value
  }

  if (typeof value === "number") {
    return value.toString()
  }

  return null
}

const createPreview = (text: string, maxLength = 280) => {
  const condensed = text.replace(/\s+/g, " ").trim()
  if (condensed.length <= maxLength) {
    return condensed
  }
  return `${condensed.slice(0, maxLength).trimEnd()}…`
}

type PromptCardProps = {
  prompt: ImagePrompt
  onViewFull?: (prompt: ImagePrompt) => void
}

const PromptCard = ({ prompt, onViewFull }: PromptCardProps) => {
  const { showSuccessToast } = useCustomToast()
  const clipboard = useClipboard(prompt.prompt_text)

  const preview = useMemo(
    () => createPreview(prompt.prompt_text),
    [prompt.prompt_text],
  )

  const attributes = useMemo(() => {
    if (!prompt.attributes || typeof prompt.attributes !== "object") {
      return [] as Array<{ key: string; value: string }>
    }

    return DISPLAY_ATTRIBUTE_KEYS.reduce<Array<{ key: string; value: string }>>(
      (accumulator, key) => {
        const value = formatAttributeValue(
          // @ts-ignore -- attributes comes from backend and can be indexed
          prompt.attributes[key],
        )
        if (value) {
          accumulator.push({ key, value })
        }
        return accumulator
      },
      [],
    )
  }, [prompt.attributes])

  const handleCopy = () => {
    clipboard.onCopy()
    showSuccessToast(
      clipboard.hasCopied ? "Prompt already copied" : "Prompt copied to clipboard",
    )
  }

  const variantLabel = `Variant ${prompt.variant_index + 1}`
  const title = prompt.title?.trim() || variantLabel

  return (
    <Box
      borderWidth="1px"
      borderRadius="lg"
      p={4}
      bg="bg.surface"
      shadow="sm"
      display="flex"
      flexDirection="column"
      gap={4}
      minH="260px"
    >
      <Stack gap={2}>
        <Flex align="center" justify="space-between">
          <Text fontWeight="bold" noOfLines={2} fontSize="sm">
            {title}
          </Text>
          <Badge colorScheme="purple" title={variantLabel}>
            #{prompt.variant_index + 1}
          </Badge>
        </Flex>
        {prompt.style_tags && prompt.style_tags.length > 0 && (
          <HStack gap={2} wrap="wrap">
            {prompt.style_tags.slice(0, 6).map((tag) => (
              <TagRoot key={tag} colorScheme="blue" variant="subtle">
                <TagLabel>{tag}</TagLabel>
              </TagRoot>
            ))}
          </HStack>
        )}
        <Text
          fontFamily="mono"
          fontSize="xs"
          whiteSpace="pre-wrap"
          noOfLines={3}
          color="fg.muted"
        >
          {preview}
        </Text>
      </Stack>

      {attributes.length > 0 && (
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={2} fontSize="xs">
          {attributes.map(({ key, value }) => (
            <Flex key={key} direction="column" gap={1}>
              <Text textTransform="uppercase" color="fg.subtle" fontSize="2xs">
                {key.replace(/_/g, " ")}
              </Text>
              <Text>{value}</Text>
            </Flex>
          ))}
        </SimpleGrid>
      )}

      <Flex justify="space-between" align="center" mt="auto" gap={2}>
        <HStack gap={2} flexWrap="wrap" fontSize="xs">
          <Badge colorScheme="gray">{prompt.model_name}</Badge>
          <Badge colorScheme="gray">{prompt.prompt_version}</Badge>
        </HStack>
        <HStack gap={2}>
          <Button size="sm" leftIcon={<Icon as={FiCopy} />} onClick={handleCopy}>
            Copy
          </Button>
          {onViewFull && (
            <Button
              size="sm"
              variant="outline"
              leftIcon={<Icon as={FiMaximize2} />}
              onClick={() => onViewFull(prompt)}
            >
              View full
            </Button>
          )}
        </HStack>
      </Flex>
    </Box>
  )
}

export default PromptCard
