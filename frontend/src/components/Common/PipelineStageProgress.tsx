import { Box, HStack, Text, VStack } from "@chakra-ui/react"

export type StageEntry = {
  status: "pending" | "running" | "completed" | "failed" | string
  items?: number
  total?: number
  unit?: string
}

type StageProgressProps = {
  stageProgress?: Record<string, StageEntry> | null
}

const STAGE_ORDER = [
  "extracting",
  "ranking",
  "generating_prompts",
  "generating_images",
] as const

const STAGE_LABELS: Record<string, string> = {
  extracting: "Extraction",
  ranking: "Ranking",
  generating_prompts: "Prompts",
  generating_images: "Images",
}

function statusIcon(status: string): string {
  switch (status) {
    case "completed":
      return "✓"
    case "running":
      return "→"
    case "failed":
      return "✗"
    default:
      return "○"
  }
}

function statusColor(status: string): string {
  switch (status) {
    case "completed":
      return "green.400"
    case "running":
      return "blue.300"
    case "failed":
      return "red.400"
    default:
      return "fg.subtle"
  }
}

function counterText(entry: StageEntry): string | null {
  if (entry.status === "pending") return null
  const { items, total, unit } = entry
  if (items !== undefined && total !== undefined) {
    return `${items} / ${total} ${unit ?? ""}`
  }
  if (items !== undefined) {
    return `${items}${unit ? ` ${unit}` : ""}`
  }
  return null
}

export function PipelineStageProgress({ stageProgress }: StageProgressProps) {
  if (!stageProgress) return null

  return (
    <VStack align="stretch" gap={1}>
      {STAGE_ORDER.map((key) => {
        const entry = stageProgress[key] as StageEntry | undefined
        const status = entry?.status ?? "pending"
        const label = STAGE_LABELS[key] ?? key
        const counter = entry ? counterText(entry) : null

        return (
          <HStack key={key} gap={2}>
            <Text
              fontSize="sm"
              color={statusColor(status)}
              minW="12px"
              fontFamily="mono"
            >
              {statusIcon(status)}
            </Text>
            <Text fontSize="sm" color="fg.muted" minW="80px">
              {label}
            </Text>
            {counter ? (
              <Text fontSize="xs" color="fg.subtle">
                {counter.trim()}
              </Text>
            ) : (
              <Box />
            )}
          </HStack>
        )
      })}
    </VStack>
  )
}
