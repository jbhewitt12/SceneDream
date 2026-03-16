import {
  Badge,
  Box,
  Button,
  Flex,
  HStack,
  Input,
  Stack,
  Text,
} from "@chakra-ui/react"

import { Field } from "@/components/ui/field"
import {
  CUSTOM_ART_STYLE_PLACEHOLDER,
  type PromptArtStyleMode,
  type PromptArtStyleSelection,
} from "@/types/promptArtStyle"

type PromptArtStyleControlProps = {
  label: string
  selection: PromptArtStyleSelection
  recommendedCount: number
  otherCount: number
  randomMixManageCopy: string
  validationMessage?: string | null
  onModeChange: (mode: PromptArtStyleMode) => void
  onTextChange: (text: string) => void
  labelColor?: string
  labelFontSize?: string
  labelTextTransform?: "uppercase" | "none"
}

export function PromptArtStyleControl({
  label,
  selection,
  recommendedCount,
  otherCount,
  randomMixManageCopy,
  validationMessage,
  onModeChange,
  onTextChange,
  labelColor = "fg.muted",
  labelFontSize = "sm",
  labelTextTransform = "none",
}: PromptArtStyleControlProps) {
  const isRandomMix = selection.promptArtStyleMode === "random_mix"

  return (
    <Stack gap={3}>
      <HStack gap={1} align="center">
        <Text
          textTransform={labelTextTransform}
          fontSize={labelFontSize}
          color={labelColor}
        >
          {label}
        </Text>
      </HStack>

      <Box
        borderWidth="1px"
        borderRadius="lg"
        p={1}
        bg="rgba(255,255,255,0.02)"
      >
        <HStack gap={1} align="stretch">
          <Button
            flex="1"
            size="sm"
            variant="ghost"
            color={isRandomMix ? "cyan.200" : "fg.muted"}
            bg={isRandomMix ? "rgba(34, 211, 238, 0.16)" : "transparent"}
            _hover={{
              bg: isRandomMix ? "rgba(34, 211, 238, 0.22)" : "whiteAlpha.100",
            }}
            onClick={() => onModeChange("random_mix")}
            aria-pressed={isRandomMix}
          >
            Random Style Mix
          </Button>
          <Button
            flex="1"
            size="sm"
            variant="ghost"
            color={!isRandomMix ? "cyan.200" : "fg.muted"}
            bg={!isRandomMix ? "rgba(34, 211, 238, 0.16)" : "transparent"}
            _hover={{
              bg: !isRandomMix ? "rgba(34, 211, 238, 0.22)" : "whiteAlpha.100",
            }}
            onClick={() => onModeChange("single_style")}
            aria-pressed={!isRandomMix}
          >
            Single art style
          </Button>
        </HStack>
      </Box>

      {isRandomMix ? (
        <Stack gap={2}>
          <Text fontSize="sm" color="fg.muted">
            Samples from the style catalog in Settings, weighted toward
            Recommended styles.
          </Text>
          <Flex gap={2} wrap="wrap" align="center">
            <Badge colorScheme="blue">{recommendedCount} recommended</Badge>
            <Badge colorScheme="gray">{otherCount} other</Badge>
            <Text fontSize="sm" color="fg.subtle">
              {randomMixManageCopy}
            </Text>
          </Flex>
        </Stack>
      ) : (
        <Stack gap={2}>
          <Text fontSize="sm" color="fg.muted">
            Uses one custom style for every scene in this run.
          </Text>
          <Field
            label="Custom art style"
            errorText={validationMessage ?? undefined}
            invalid={Boolean(validationMessage)}
          >
            <Input
              value={selection.promptArtStyleText}
              onChange={(event) => onTextChange(event.target.value)}
              placeholder={CUSTOM_ART_STYLE_PLACEHOLDER}
            />
          </Field>
        </Stack>
      )}
    </Stack>
  )
}
