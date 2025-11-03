import { Box, Button, HStack, Spinner, Stack, Text } from "@chakra-ui/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useState } from "react"
import { FiCheck } from "react-icons/fi"

import type { GeneratedImageWithContext } from "@/api/generatedImages"
import {
  type ImagePromptMetadataRead,
  type MetadataUpdateRequest,
  type MetadataVariant,
  generatePromptMetadata,
  updatePromptMetadata,
} from "@/api/imagePrompts"
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogHeader,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog"
import useCustomToast from "@/hooks/useCustomToast"

type MetadataRegenerationModalProps = {
  isOpen: boolean
  onClose: () => void
  promptId: string | null
  imageId: string | null
}

type UpdatePayload = {
  promptId: string
  metadata: MetadataUpdateRequest
}

const MetadataRegenerationModal = ({
  isOpen,
  onClose,
  promptId,
  imageId,
}: MetadataRegenerationModalProps) => {
  const queryClient = useQueryClient()
  const { showErrorToast, showSuccessToast } = useCustomToast()
  const [variants, setVariants] = useState<MetadataVariant[]>([])
  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchVariants = useCallback(
    async (abortToken?: { cancelled: boolean }) => {
      if (!promptId) {
        setVariants([])
        setError("Metadata regeneration requires a prompt.")
        setIsGenerating(false)
        return
      }

      setIsGenerating(true)
      setError(null)
      setVariants([])
      try {
        const response = await generatePromptMetadata(promptId)
        if (abortToken?.cancelled) return
        setVariants(response.variants ?? [])
      } catch (err) {
        if (abortToken?.cancelled) return
        const message =
          err instanceof Error ? err.message : "Failed to generate metadata."
        setError(message)
      } finally {
        if (!abortToken?.cancelled) {
          setIsGenerating(false)
        }
      }
    },
    [promptId],
  )

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const token = { cancelled: false }
    void fetchVariants(token)
    return () => {
      token.cancelled = true
    }
  }, [fetchVariants, isOpen])

  const updateMutation = useMutation<
    ImagePromptMetadataRead,
    Error,
    UpdatePayload
  >({
    mutationFn: async ({ promptId, metadata }: UpdatePayload) =>
      updatePromptMetadata(promptId, metadata),
    onSuccess: (data) => {
      const updatedTitle = data.title ?? null
      const updatedFlavour = data.flavour_text ?? null

      if (imageId) {
        queryClient.setQueryData<GeneratedImageWithContext | undefined>(
          ["generated-image", imageId],
          (cached) => {
            if (!cached) {
              return cached
            }

            return {
              ...cached,
              image: {
                ...cached.image,
                prompt_title: updatedTitle,
                prompt_flavour_text: updatedFlavour,
              },
              prompt: cached.prompt
                ? {
                    ...cached.prompt,
                    title: updatedTitle,
                    flavour_text: updatedFlavour,
                  }
                : cached.prompt,
            }
          },
        )
      }

      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) &&
          query.queryKey.length > 0 &&
          query.queryKey[0] === "generated-images",
      })

      showSuccessToast("Prompt metadata updated.")
      onClose()
    },
    onError: (err) => {
      showErrorToast(err.message)
    },
  })

  const handleUseVariant = (variant: MetadataVariant) => {
    if (!promptId || updateMutation.isPending) {
      return
    }

    updateMutation.mutate({
      promptId,
      metadata: {
        title: variant.title,
        flavour_text: variant.flavour_text,
      },
    })
  }

  const hasVariants = variants.length > 0

  return (
    <DialogRoot
      open={isOpen}
      onOpenChange={(details) => {
        if (!details.open) {
          onClose()
        }
      }}
      size="lg"
    >
      <DialogContent>
        <DialogCloseTrigger />
        <DialogHeader>
          <DialogTitle>Regenerate Title &amp; Flavour Text</DialogTitle>
        </DialogHeader>
        <DialogBody>
          {!promptId ? (
            <Stack align="center" py={8} gap={3}>
              <Text color="fg.muted" textAlign="center">
                This image is missing prompt metadata. Regeneration is
                unavailable.
              </Text>
              <Button size="sm" onClick={onClose}>
                Close
              </Button>
            </Stack>
          ) : isGenerating ? (
            <Stack align="center" py={8} gap={4}>
              <Spinner size="lg" />
              <Text color="fg.muted">Generating creative variations...</Text>
            </Stack>
          ) : error ? (
            <Stack align="center" py={8} gap={4}>
              <Text color="red.500" fontWeight="semibold">
                Failed to generate variants
              </Text>
              <Text fontSize="sm" color="fg.muted" textAlign="center">
                {error}
              </Text>
              <Button
                size="sm"
                colorPalette="purple"
                onClick={() => {
                  void fetchVariants()
                }}
              >
                Try Again
              </Button>
            </Stack>
          ) : !hasVariants ? (
            <Stack align="center" py={8} gap={3}>
              <Text color="fg.muted">No metadata variants were returned.</Text>
              <Button
                size="sm"
                colorPalette="purple"
                onClick={() => {
                  void fetchVariants()
                }}
              >
                Regenerate
              </Button>
            </Stack>
          ) : (
            <Stack gap={3}>
              {variants.map((variant, index) => (
                <Box
                  key={`${variant.title}-${variant.flavour_text}-${index}`}
                  p={4}
                  borderWidth="1px"
                  borderRadius="md"
                  bg="rgba(255,255,255,0.02)"
                  _hover={{ bg: "rgba(255,255,255,0.04)" }}
                >
                  <HStack justify="space-between" align="start" gap={4}>
                    <Stack gap={2} flex="1">
                      {variant.title && (
                        <Text fontWeight="semibold" fontSize="md">
                          {variant.title}
                        </Text>
                      )}
                      {variant.flavour_text && (
                        <Text
                          fontSize="sm"
                          color="fg.subtle"
                          fontStyle="italic"
                        >
                          {variant.flavour_text}
                        </Text>
                      )}
                    </Stack>
                    <Button
                      size="sm"
                      colorPalette="purple"
                      onClick={() => handleUseVariant(variant)}
                      loading={updateMutation.isPending}
                      loadingText="Applying"
                      disabled={!variant.title && !variant.flavour_text}
                    >
                      <HStack gap={1} align="center">
                        <FiCheck aria-hidden="true" />
                        <Text as="span">Use</Text>
                      </HStack>
                    </Button>
                  </HStack>
                </Box>
              ))}
            </Stack>
          )}
        </DialogBody>
      </DialogContent>
    </DialogRoot>
  )
}

export default MetadataRegenerationModal
