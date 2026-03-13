import {
  Box,
  Input,
  NativeSelectField,
  NativeSelectIndicator,
  NativeSelectRoot,
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
  return (
    <Stack gap={3}>
      <Box>
        <Text
          textTransform={labelTextTransform}
          fontSize={labelFontSize}
          color={labelColor}
          mb={1}
        >
          {label}
        </Text>
        <NativeSelectRoot w="full">
          <NativeSelectField
            value={selection.promptArtStyleMode}
            onChange={(event) =>
              onModeChange(event.target.value as PromptArtStyleMode)
            }
          >
            <option value="random_mix">Random Style Mix</option>
            <option value="single_style">Single art style</option>
          </NativeSelectField>
          <NativeSelectIndicator />
        </NativeSelectRoot>
      </Box>

      {selection.promptArtStyleMode === "random_mix" ? (
        <Box p={3} borderWidth="1px" borderRadius="md" bg="bg.subtle">
          <Stack gap={1}>
            <Text fontSize="sm" color="fg.muted">
              Randomly samples from the art styles in Settings, weighted toward
              Recommended styles.
            </Text>
            <Text fontSize="sm" color="fg.muted">
              Current catalog: {recommendedCount} recommended, {otherCount}{" "}
              other.
            </Text>
            <Text fontSize="sm" color="fg.muted">
              {randomMixManageCopy}
            </Text>
          </Stack>
        </Box>
      ) : (
        <Field
          label="Custom art style"
          helperText="This style will be used for every scene in this run."
          errorText={validationMessage ?? undefined}
          invalid={Boolean(validationMessage)}
        >
          <Input
            value={selection.promptArtStyleText}
            onChange={(event) => onTextChange(event.target.value)}
            placeholder={CUSTOM_ART_STYLE_PLACEHOLDER}
          />
        </Field>
      )}
    </Stack>
  )
}
