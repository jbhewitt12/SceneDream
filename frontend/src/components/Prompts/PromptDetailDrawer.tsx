import {
  Badge,
  Box,
  Button,
  DrawerBackdrop,
  DrawerBody,
  DrawerCloseTrigger,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerRoot,
  DrawerTitle,
  HStack,
  Heading,
  SimpleGrid,
  Stack,
  Text,
} from "@chakra-ui/react"

import type { ImagePrompt } from "@/api/imagePrompts"
import SceneContextPanel from "@/components/Prompts/SceneContextPanel"

type PromptDetailDrawerProps = {
  prompt: ImagePrompt | null
  isOpen: boolean
  onClose: () => void
}

const PromptDetailDrawer = ({
  prompt,
  isOpen,
  onClose,
}: PromptDetailDrawerProps) => {
  if (!prompt) {
    return null
  }

  const attributeEntries = Object.entries(prompt.attributes ?? {}).filter(
    ([, value]) => typeof value === "string" || Array.isArray(value),
  )

  return (
    <DrawerRoot
      open={isOpen}
      onOpenChange={(event) => !event.open && onClose()}
    >
      <DrawerBackdrop />
      <DrawerContent maxW="720px">
        <DrawerCloseTrigger />
        <DrawerHeader>
          <DrawerTitle>Prompt variant #{prompt.variant_index + 1}</DrawerTitle>
        </DrawerHeader>
        <DrawerBody>
          <Stack gap={4}>
            <Box>
              <Heading size="sm" mb={2}>
                Prompt text
              </Heading>
              <Text fontFamily="mono" whiteSpace="pre-wrap" fontSize="sm">
                {prompt.prompt_text}
              </Text>
            </Box>
            {prompt.style_tags && prompt.style_tags.length > 0 && (
              <HStack gap={2} wrap="wrap">
                {prompt.style_tags.map((tag) => (
                  <Badge key={tag} colorScheme="purple" variant="subtle">
                    {tag}
                  </Badge>
                ))}
              </HStack>
            )}
            {attributeEntries.length > 0 && (
              <Box>
                <Heading size="sm" mb={2}>
                  Attributes
                </Heading>
                <SimpleGrid columns={{ base: 1, md: 2 }} gap={3} fontSize="sm">
                  {attributeEntries.map(([key, value]) => (
                    <Stack key={key} gap={1}>
                      <Text
                        textTransform="uppercase"
                        color="fg.subtle"
                        fontSize="xs"
                      >
                        {key.replace(/_/g, " ")}
                      </Text>
                      <Text>
                        {Array.isArray(value)
                          ? value
                              .filter((item) => typeof item === "string")
                              .join(", ")
                          : String(value)}
                      </Text>
                    </Stack>
                  ))}
                </SimpleGrid>
              </Box>
            )}
            <SceneContextPanel
              scene={prompt.scene}
              contextWindow={prompt.context_window}
            />
          </Stack>
        </DrawerBody>
        <DrawerFooter>
          <Button onClick={onClose}>Close</Button>
        </DrawerFooter>
      </DrawerContent>
    </DrawerRoot>
  )
}

export default PromptDetailDrawer
