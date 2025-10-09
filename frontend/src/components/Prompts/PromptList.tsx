import {
  Box,
  Center,
  Flex,
  Spinner,
  Text,
  useBreakpointValue,
} from "@chakra-ui/react"
import {
  type ReactNode,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"

import type { ImagePrompt } from "@/api/imagePrompts"
import PromptCard from "@/components/Prompts/PromptCard"
import {
  PaginationItems,
  PaginationNextTrigger,
  PaginationPrevTrigger,
  PaginationRoot,
} from "@/components/ui/pagination"

const ESTIMATED_ROW_HEIGHT = 320
const OVERSCAN_ROWS = 2

const getVirtualRows = (
  prompts: ImagePrompt[],
  columnCount: number,
  scrollOffset: number,
  viewportHeight: number,
) => {
  if (!prompts.length) {
    return [] as Array<{
      rowIndex: number
      top: number
      items: ImagePrompt[]
    }>
  }

  const rowCount = Math.ceil(prompts.length / columnCount)
  const startRow = Math.max(
    0,
    Math.floor(scrollOffset / ESTIMATED_ROW_HEIGHT) - OVERSCAN_ROWS,
  )
  const endRow = Math.min(
    rowCount,
    Math.ceil((scrollOffset + viewportHeight) / ESTIMATED_ROW_HEIGHT) +
      OVERSCAN_ROWS,
  )

  const rows: Array<{ rowIndex: number; top: number; items: ImagePrompt[] }> = []

  for (let rowIndex = startRow; rowIndex < endRow; rowIndex += 1) {
    const startIndex = rowIndex * columnCount
    const endIndex = startIndex + columnCount
    rows.push({
      rowIndex,
      top: rowIndex * ESTIMATED_ROW_HEIGHT,
      items: prompts.slice(startIndex, endIndex),
    })
  }

  return rows
}

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
  const scrollContainerRef = useRef<HTMLDivElement | null>(null)
  const [scrollOffset, setScrollOffset] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(600)

  const columnCount =
    useBreakpointValue({ base: 1, md: 2, xl: 3 }, { fallback: "base" }) ?? 1

  const page = pagination?.page ?? 1
  const pageSize = pagination?.pageSize
  const hasNextPage = pagination?.hasNextPage ?? false

  useEffect(() => {
    const element = scrollContainerRef.current
    if (!element) {
      return
    }

    const updateDimensions = () => {
      setViewportHeight(element.clientHeight)
    }

    updateDimensions()

    const observer = new ResizeObserver(updateDimensions)
    observer.observe(element)

    return () => {
      observer.disconnect()
    }
  }, [])

  const handleScroll = () => {
    const element = scrollContainerRef.current
    if (!element) {
      return
    }
    setScrollOffset(element.scrollTop)
  }

  useEffect(() => {
    const element = scrollContainerRef.current
    if (!element) {
      return
    }
    element.addEventListener("scroll", handleScroll, { passive: true })
    return () => element.removeEventListener("scroll", handleScroll)
  }, [])

  useEffect(() => {
    const element = scrollContainerRef.current
    if (!element) {
      return
    }
    element.scrollTop = 0
    setScrollOffset(0)
  }, [prompts.length, columnCount, page])

  const virtualRows = useMemo(
    () =>
      getVirtualRows(prompts, columnCount, scrollOffset, viewportHeight),
    [prompts, columnCount, scrollOffset, viewportHeight],
  )

  const totalHeight = useMemo(() => {
    if (!prompts.length) {
      return 0
    }
    const rowCount = Math.ceil(prompts.length / columnCount)
    return rowCount * ESTIMATED_ROW_HEIGHT
  }, [prompts, columnCount])

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
        ref={scrollContainerRef}
        overflowY="auto"
        h={height}
        borderWidth="1px"
        borderRadius="lg"
        bg="bg.surface"
        shadow="sm"
        px={2}
      >
        <Box height={totalHeight} position="relative">
          {virtualRows.map(({ rowIndex, top, items }) => (
            <Box
              key={rowIndex}
              position="absolute"
              top={`${top}px`}
              left={0}
              width="100%"
              px={2}
            >
              <Flex
                gap={4}
                flexWrap="wrap"
                justify={{ base: "center", md: "flex-start" }}
              >
                {items.map((prompt) => (
                  <Box key={prompt.id} flex={{ base: "1 1 100%", md: "1 1 calc(50% - 1rem)", xl: "1 1 calc(33.333% - 1rem)" }} minW={0}>
                    <PromptCard prompt={prompt} onViewFull={onViewPrompt} />
                  </Box>
                ))}
              </Flex>
            </Box>
          ))}
        </Box>
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
