import { Box, Center, Flex, SimpleGrid, Spinner, Text } from "@chakra-ui/react"
import type { ReactNode } from "react"

import type { ImagePrompt } from "@/api/imagePrompts"
import PromptCard from "@/components/Prompts/PromptCard"
import {
  PaginationItems,
  PaginationNextTrigger,
  PaginationPrevTrigger,
  PaginationRoot,
} from "@/components/ui/pagination"

type PromptListPagination = {
  page: number
  pageSize: number
  hasNextPage: boolean
  onPageChange: (page: number) => void
}

type PromptListProps = {
  prompts: ImagePrompt[]
  isLoading?: boolean
  pagination?: PromptListPagination
  height?: number | string
  emptyState?: ReactNode
  onViewPrompt?: (prompt: ImagePrompt) => void
}

const PromptList = ({
  prompts,
  isLoading,
  pagination,
  height = "100%",
  emptyState,
  onViewPrompt,
}: PromptListProps) => {
  const page = pagination?.page ?? 1
  const pageSize = pagination?.pageSize
  const hasNextPage = pagination?.hasNextPage ?? false

  if (isLoading) {
    return (
      <Center h="100%">
        <Spinner size="lg" />
      </Center>
    )
  }

  if (!prompts.length) {
    return (
      <Center h="100%" textAlign="center">
        {emptyState ?? <Text>No prompts available yet.</Text>}
      </Center>
    )
  }

  return (
    <Flex direction="column" gap={4} h="100%">
      <Box
        overflowY="auto"
        h={height}
        borderWidth="1px"
        borderRadius="lg"
        bg="bg.surface"
        shadow="sm"
        px={2}
      >
        <SimpleGrid columns={{ base: 1, md: 2 }} spacing={4} p={2}>
          {prompts.map((prompt) => (
            <Box key={prompt.id} minW={0}>
              <PromptCard prompt={prompt} />
            </Box>
          ))}
        </SimpleGrid>
      </Box>
      {pagination && pageSize && (
        <Flex justify="flex-end">
          <PaginationRoot
            count={
              hasNextPage
                ? page * pageSize + pageSize
                : (page - 1) * pageSize + prompts.length
            }
            page={page}
            pageSize={pageSize}
            onPageChange={({ page: nextPage }) =>
              pagination.onPageChange(nextPage)
            }
          >
            <Flex>
              <PaginationPrevTrigger disabled={page <= 1} />
              <PaginationItems />
              <PaginationNextTrigger
                disabled={!hasNextPage && prompts.length < pageSize}
              />
            </Flex>
          </PaginationRoot>
        </Flex>
      )}
    </Flex>
  )
}

export default PromptList
