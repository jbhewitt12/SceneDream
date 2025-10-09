import {
  Badge,
  Box,
  Button,
  Collapsible,
  Separator,
  Flex,
  Heading,
  Icon,
  SimpleGrid,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useState } from "react"
import { FiChevronDown, FiChevronUp } from "react-icons/fi"

import type { ImagePrompt } from "@/api/imagePrompts"

const formatParagraphSpan = (span: [number, number] | null) => {
  if (!span) {
    return "—"
  }
  return `${span[0]} → ${span[1]}`
}

type SceneContextPanelProps = {
  scene: ImagePrompt["scene"] | null | undefined
  contextWindow: ImagePrompt["context_window"]
}

const SceneContextPanel = ({ scene, contextWindow }: SceneContextPanelProps) => {
  const [open, setOpen] = useState(false)

  const toggleOpen = () => setOpen((prev) => !prev)

  return (
    <Box borderWidth="1px" borderRadius="lg" bg="bg.surface" shadow="sm">
      <Flex
        align="center"
        justify="space-between"
        px={4}
        py={3}
        cursor="pointer"
        onClick={toggleOpen}
      >
        <Stack>
          <Heading size="sm">Scene context</Heading>
          {scene && (
            <Text fontSize="sm" color="fg.subtle">
              {scene.book_slug} · Chapter {scene.chapter_number} · Scene {" "}
              {scene.scene_number}
            </Text>
          )}
        </Stack>
        <Button
          size="sm"
          variant="ghost"
          rightIcon={<Icon as={open ? FiChevronUp : FiChevronDown} />}
          onClick={(event) => {
            event.stopPropagation()
            toggleOpen()
          }}
        >
          {open ? "Hide" : "Show"}
        </Button>
      </Flex>
      <Collapsible.Root open={open}>
        <Collapsible.Content>
          <Separator />
          <Stack px={4} py={4} gap={3} fontSize="sm">
          {scene ? (
            <SimpleGrid columns={{ base: 1, md: 2 }} gap={3}>
              <Stack spacing={1}>
                <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                  Chapter
                </Text>
                <Text>
                  #{scene.chapter_number} · {scene.chapter_title}
                </Text>
              </Stack>
              <Stack spacing={1}>
                <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                  Scene
                </Text>
                <Text>#{scene.scene_number}</Text>
              </Stack>
              <Stack spacing={1}>
                <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                  Book
                </Text>
                <Text>{scene.book_slug}</Text>
              </Stack>
              <Stack spacing={1}>
                <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                  Location Marker
                </Text>
                <Text>{scene.location_marker}</Text>
              </Stack>
            </SimpleGrid>
          ) : (
            <Text>No scene metadata provided.</Text>
          )}
          <Separator />
          <SimpleGrid columns={{ base: 1, md: 3 }} gap={3}>
            <Stack spacing={1}>
              <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                Paragraph span
              </Text>
              <Text>{formatParagraphSpan(contextWindow.paragraphSpan ?? null)}</Text>
            </Stack>
            <Stack spacing={1}>
              <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                Context
              </Text>
              <Text>
                {contextWindow.paragraphsBefore ?? 0} before · {" "}
                {contextWindow.paragraphsAfter ?? 0} after
              </Text>
            </Stack>
            <Stack spacing={1}>
              <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                Chapter number
              </Text>
              <Text>{contextWindow.chapterNumber ?? "—"}</Text>
            </Stack>
          </SimpleGrid>
          {contextWindow.extras && (
            <Stack spacing={2}>
              <Text textTransform="uppercase" color="fg.subtle" fontSize="xs">
                Additional metadata
              </Text>
              <SimpleGrid columns={{ base: 1, md: 2 }} gap={2}>
                {Object.entries(contextWindow.extras).map(([key, value]) => (
                  <Badge key={key} variant="subtle" colorScheme="gray" px={3} py={1}>
                    {key}: {String(value)}
                  </Badge>
                ))}
              </SimpleGrid>
            </Stack>
          )}
          </Stack>
        </Collapsible.Content>
      </Collapsible.Root>
    </Box>
  )
}

export default SceneContextPanel
