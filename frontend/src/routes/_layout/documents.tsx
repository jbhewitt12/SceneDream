import {
  AlertContent,
  AlertIndicator,
  AlertRoot,
  Badge,
  Box,
  Button,
  Container,
  Flex,
  Grid,
  HStack,
  Heading,
  Input,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"
import { FiRefreshCcw, FiSearch } from "react-icons/fi"

import { type DocumentDashboardEntry, DocumentsApi } from "@/api/documents"

export const Route = createFileRoute("/_layout/documents")({
  component: DocumentsPage,
})

const formatDateTime = (value: string | null | undefined) => {
  if (!value) {
    return "—"
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed)
}

const statusColor = (status: string | null | undefined) => {
  if (!status) {
    return "gray"
  }
  if (status === "completed") {
    return "green"
  }
  if (status === "failed") {
    return "red"
  }
  if (status === "pending") {
    return "yellow"
  }
  return "blue"
}

const stageColor = (completed: boolean) => (completed ? "green" : "gray")

function DocumentsPage() {
  const [search, setSearch] = useState("")
  const dashboardQuery = useQuery({
    queryKey: ["documents", "dashboard"],
    queryFn: () => DocumentsApi.getDashboard(),
    refetchInterval: 10000,
  })

  const filteredEntries = useMemo(() => {
    const rows = dashboardQuery.data?.data ?? []
    const term = search.trim().toLowerCase()
    if (!term) {
      return rows
    }
    return rows.filter((row) =>
      [row.display_name, row.source_path, row.slug].some((value) =>
        value.toLowerCase().includes(term),
      ),
    )
  }, [dashboardQuery.data?.data, search])

  return (
    <Container maxW="6xl" py={6}>
      <Stack gap={6}>
        <Flex align="center" justify="space-between" wrap="wrap" gap={3}>
          <Stack gap={1}>
            <Heading size="lg">Documents Dashboard</Heading>
            <Text color="fg.muted">
              Source files and end-to-end pipeline status at a glance.
            </Text>
          </Stack>
          <Button
            variant="outline"
            gap={2}
            onClick={() => dashboardQuery.refetch()}
            loading={dashboardQuery.isFetching}
          >
            <FiRefreshCcw />
            Refresh
          </Button>
        </Flex>

        <HStack gap={3} align="stretch">
          <Box position="relative" flex="1">
            <Box
              position="absolute"
              left={3}
              top="50%"
              transform="translateY(-50%)"
            >
              <FiSearch />
            </Box>
            <Input
              pl={9}
              placeholder="Search by file, path, or slug"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </Box>
          <Badge alignSelf="center" colorScheme="blue" px={3} py={1}>
            {filteredEntries.length} shown
          </Badge>
        </HStack>

        {dashboardQuery.isLoading ? (
          <Flex justify="center" py={12}>
            <Spinner size="lg" />
          </Flex>
        ) : null}

        {dashboardQuery.error ? (
          <AlertRoot status="error">
            <AlertIndicator />
            <AlertContent>
              {dashboardQuery.error instanceof Error
                ? dashboardQuery.error.message
                : "Failed to load document dashboard."}
            </AlertContent>
          </AlertRoot>
        ) : null}

        {!dashboardQuery.isLoading &&
        !dashboardQuery.error &&
        !filteredEntries.length ? (
          <Box borderWidth="1px" borderRadius="lg" p={6}>
            <Text color="fg.muted">
              No documents matched your search or no files were found in
              `documents/`.
            </Text>
          </Box>
        ) : null}

        <Stack gap={4}>
          {filteredEntries.map((entry) => (
            <DocumentCard
              key={`${entry.source_path}:${entry.slug}`}
              entry={entry}
            />
          ))}
        </Stack>
      </Stack>
    </Container>
  )
}

function DocumentCard({ entry }: { entry: DocumentDashboardEntry }) {
  return (
    <Box
      p={5}
      borderWidth="1px"
      borderRadius="lg"
      bg="rgba(255,255,255,0.04)"
      backdropFilter="blur(8px) saturate(140%)"
    >
      <Stack gap={4}>
        <Flex justify="space-between" align="center" wrap="wrap" gap={2}>
          <Stack gap={0}>
            <Heading size="md">{entry.display_name}</Heading>
            <Text fontSize="sm" color="fg.muted">
              {entry.source_path}
            </Text>
          </Stack>
          <HStack gap={2}>
            <Badge colorScheme="purple">
              {entry.source_type.toUpperCase()}
            </Badge>
            <Badge colorScheme={entry.file_exists ? "green" : "red"}>
              {entry.file_exists ? "File found" : "File missing"}
            </Badge>
            <Badge colorScheme="gray">{entry.slug}</Badge>
          </HStack>
        </Flex>

        <Grid templateColumns={{ base: "1fr", md: "repeat(4, 1fr)" }} gap={3}>
          <StageBadge
            label="Extracted"
            count={entry.counts.extracted}
            complete={entry.stages.extracted}
          />
          <StageBadge
            label="Ranked"
            count={entry.counts.ranked}
            complete={entry.stages.ranked}
          />
          <StageBadge
            label="Prompts"
            count={entry.counts.prompts_generated}
            complete={entry.stages.prompts_generated}
          />
          <StageBadge
            label="Images"
            count={entry.counts.images_generated}
            complete={entry.stages.images_generated}
          />
        </Grid>

        <Grid templateColumns={{ base: "1fr", md: "repeat(2, 1fr)" }} gap={3}>
          <Box borderWidth="1px" borderRadius="md" p={3}>
            <Text
              fontSize="xs"
              textTransform="uppercase"
              color="fg.subtle"
              mb={1}
            >
              Ingestion
            </Text>
            <HStack gap={2}>
              <Badge colorScheme={statusColor(entry.ingestion_state)}>
                {entry.ingestion_state ?? "unknown"}
              </Badge>
              {entry.ingestion_error ? (
                <Text fontSize="sm" color="red.300">
                  {entry.ingestion_error}
                </Text>
              ) : (
                <Text fontSize="sm" color="fg.muted">
                  No ingestion errors.
                </Text>
              )}
            </HStack>
          </Box>

          <Box borderWidth="1px" borderRadius="md" p={3}>
            <Text
              fontSize="xs"
              textTransform="uppercase"
              color="fg.subtle"
              mb={1}
            >
              Last Run
            </Text>
            {entry.last_run ? (
              <Stack gap={1}>
                <HStack gap={2}>
                  <Badge colorScheme={statusColor(entry.last_run.status)}>
                    {entry.last_run.status}
                  </Badge>
                  <Text fontSize="sm" color="fg.muted">
                    Stage: {entry.last_run.current_stage ?? "—"}
                  </Text>
                </HStack>
                <Text fontSize="sm" color="fg.muted">
                  Completed: {formatDateTime(entry.last_run.completed_at)}
                </Text>
                {entry.last_run.error_message ? (
                  <Text fontSize="sm" color="red.300">
                    {entry.last_run.error_message}
                  </Text>
                ) : null}
              </Stack>
            ) : (
              <Text fontSize="sm" color="fg.muted">
                No pipeline runs yet.
              </Text>
            )}
          </Box>
        </Grid>
      </Stack>
    </Box>
  )
}

function StageBadge({
  label,
  count,
  complete,
}: {
  label: string
  count: number
  complete: boolean
}) {
  return (
    <Box borderWidth="1px" borderRadius="md" p={3}>
      <HStack justify="space-between" align="center">
        <Text fontSize="sm" color="fg.muted">
          {label}
        </Text>
        <Badge colorScheme={stageColor(complete)}>{count}</Badge>
      </HStack>
    </Box>
  )
}
