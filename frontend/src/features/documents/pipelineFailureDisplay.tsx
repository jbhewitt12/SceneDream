import { Box, Stack, Text } from "@chakra-ui/react"
import React from "react"

void React

type PipelineErrorLike = {
  message?: string | null
  metadata?: Record<string, unknown> | null
}

type PipelineRunFailureLike = {
  error?: PipelineErrorLike | null
  error_message?: string | null
  usage_summary?: Record<string, unknown>
}

export type PipelineFailureDisplay = {
  message: string | null
  hint: string | null
  actionItems: string[]
  secondaryMessages: string[]
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null

const coercePipelineError = (value: unknown): PipelineErrorLike | null => {
  if (!isRecord(value)) {
    return null
  }

  const message = typeof value.message === "string" ? value.message : undefined
  const metadata = isRecord(value.metadata) ? value.metadata : undefined

  if (!message && !metadata) {
    return null
  }

  return {
    message,
    metadata,
  }
}

const extractStructuredError = (
  usageSummary: Record<string, unknown> | undefined,
): PipelineErrorLike | null => {
  if (!usageSummary) {
    return null
  }

  const directFailure = coercePipelineError(usageSummary.failure)
  if (directFailure) {
    return directFailure
  }

  const diagnostics = usageSummary.diagnostics
  if (!isRecord(diagnostics)) {
    return null
  }

  return coercePipelineError(diagnostics.error)
}

const toActionItems = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return []
  }

  return value.filter(
    (item): item is string =>
      typeof item === "string" && item.trim().length > 0,
  )
}

export const getPipelineFailureDisplay = (
  runSummary: PipelineRunFailureLike,
  secondaryMessages: string[] = [],
): PipelineFailureDisplay | null => {
  const structuredError =
    coercePipelineError(runSummary.error) ??
    extractStructuredError(runSummary.usage_summary)
  const metadata = structuredError?.metadata ?? null

  const message =
    structuredError?.message?.trim() || runSummary.error_message?.trim() || null
  const hint =
    metadata &&
    typeof metadata.hint === "string" &&
    metadata.hint.trim().length > 0
      ? metadata.hint.trim()
      : null
  const actionItems = toActionItems(metadata?.action_items)

  if (
    !message &&
    !hint &&
    actionItems.length === 0 &&
    secondaryMessages.length === 0
  ) {
    return null
  }

  return {
    message,
    hint,
    actionItems,
    secondaryMessages,
  }
}

export function PipelineFailureNotice({
  failure,
}: {
  failure: PipelineFailureDisplay | null
}) {
  if (!failure) {
    return null
  }

  return (
    <Stack gap={1}>
      {failure.message ? (
        <Text fontSize="sm" color="red.300">
          {failure.message}
        </Text>
      ) : null}
      {failure.hint ? (
        <Text fontSize="sm" color="orange.300">
          {failure.hint}
        </Text>
      ) : null}
      {failure.actionItems.length > 0 ? (
        <Box as="ul" pl={5} fontSize="sm" color="fg.muted">
          {failure.actionItems.map((item) => (
            <Box as="li" key={item}>
              {item}
            </Box>
          ))}
        </Box>
      ) : null}
      {failure.secondaryMessages.map((message) => (
        <Text key={message} fontSize="sm" color="red.300">
          {message}
        </Text>
      ))}
    </Stack>
  )
}
