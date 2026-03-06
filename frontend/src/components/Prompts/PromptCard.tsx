import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  SimpleGrid,
  Stack,
  TagLabel,
  TagRoot,
  Text,
  useClipboard,
} from "@chakra-ui/react"
import { useMemo, useState } from "react"
import { FiCopy } from "react-icons/fi"

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

// Preview truncation removed per new design requirements

type PromptCardProps = {
  prompt: ImagePrompt
}

const PromptCard = ({ prompt }: PromptCardProps) => {
  const { showSuccessToast } = useCustomToast()
  const clipboard = useClipboard({ value: prompt.prompt_text })
  const [expanded, setExpanded] = useState(false)

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
    const alreadyCopied = clipboard.copied
    clipboard.copy()
    showSuccessToast(
      alreadyCopied ? "Prompt already copied" : "Prompt copied to clipboard",
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
      cursor="pointer"
      onClick={() => setExpanded((prev) => !prev)}
      aria-expanded={expanded}
    >
      <Stack gap={2}>
        <Flex align="center" justify="space-between">
          <Text fontWeight="bold" lineClamp={2} fontSize="sm">
            {title}
          </Text>
          <Badge colorScheme="purple" title={variantLabel}>
            #{prompt.variant_index + 1}
          </Badge>
        </Flex>
        {expanded && prompt.style_tags && prompt.style_tags.length > 0 && (
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
          color="fg.muted"
        >
          {prompt.prompt_text}
        </Text>
      </Stack>

      {expanded && attributes.length > 0 && (
        <SimpleGrid columns={{ base: 1, md: 2 }} gap={2} fontSize="xs">
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
          <Button
            size="sm"
            onClick={(e) => {
              e.stopPropagation()
              handleCopy()
            }}
          >
            <HStack gap={1} align="center">
              <FiCopy aria-hidden="true" />
              <Text as="span">Copy</Text>
            </HStack>
          </Button>
        </HStack>
      </Flex>
    </Box>
  )
}

export default PromptCard
