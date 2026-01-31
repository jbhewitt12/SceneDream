import {
  Box,
  Button,
  HStack,
  Image,
  Spinner,
  Stack,
  Text,
} from "@chakra-ui/react"
import { useCallback, useRef, useState } from "react"
import ReactCrop, { type Crop, type PixelCrop } from "react-image-crop"
import "react-image-crop/dist/ReactCrop.css"

import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogHeader,
  DialogRoot,
  DialogTitle,
} from "@/components/ui/dialog"

type CropModalProps = {
  isOpen: boolean
  onClose: () => void
  imageSrc: string
  onCropComplete: (croppedBlob: Blob) => Promise<void>
}

const CropModal = ({
  isOpen,
  onClose,
  imageSrc,
  onCropComplete,
}: CropModalProps) => {
  const [crop, setCrop] = useState<Crop>()
  const [completedCrop, setCompletedCrop] = useState<PixelCrop>()
  const [isApplying, setIsApplying] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const imgRef = useRef<HTMLImageElement>(null)

  const generatePreview = useCallback((pixelCrop: PixelCrop) => {
    if (!imgRef.current || !pixelCrop.width || !pixelCrop.height) {
      setPreviewUrl(null)
      return
    }

    const image = imgRef.current
    const canvas = document.createElement("canvas")
    const ctx = canvas.getContext("2d")
    if (!ctx) {
      return
    }

    const scaleX = image.naturalWidth / image.width
    const scaleY = image.naturalHeight / image.height

    canvas.width = pixelCrop.width * scaleX
    canvas.height = pixelCrop.height * scaleY

    ctx.drawImage(
      image,
      pixelCrop.x * scaleX,
      pixelCrop.y * scaleY,
      pixelCrop.width * scaleX,
      pixelCrop.height * scaleY,
      0,
      0,
      canvas.width,
      canvas.height,
    )

    setPreviewUrl(canvas.toDataURL())
  }, [])

  const handleCropComplete = useCallback(
    (pixelCrop: PixelCrop) => {
      setCompletedCrop(pixelCrop)
      generatePreview(pixelCrop)
    },
    [generatePreview],
  )

  const handleApply = useCallback(async () => {
    if (!imgRef.current || !completedCrop?.width || !completedCrop?.height) {
      return
    }

    setIsApplying(true)

    try {
      const image = imgRef.current
      const canvas = document.createElement("canvas")
      const ctx = canvas.getContext("2d")
      if (!ctx) {
        throw new Error("Failed to get canvas context")
      }

      const scaleX = image.naturalWidth / image.width
      const scaleY = image.naturalHeight / image.height

      canvas.width = completedCrop.width * scaleX
      canvas.height = completedCrop.height * scaleY

      ctx.drawImage(
        image,
        completedCrop.x * scaleX,
        completedCrop.y * scaleY,
        completedCrop.width * scaleX,
        completedCrop.height * scaleY,
        0,
        0,
        canvas.width,
        canvas.height,
      )

      // Detect format from URL - default to PNG for lossless quality
      const isPng = imageSrc.toLowerCase().includes(".png")
      const mimeType = isPng ? "image/png" : "image/jpeg"
      const quality = isPng ? undefined : 1.0

      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(
          (b) => {
            if (b) {
              resolve(b)
            } else {
              reject(new Error("Failed to create blob from canvas"))
            }
          },
          mimeType,
          quality,
        )
      })

      await onCropComplete(blob)
    } finally {
      setIsApplying(false)
    }
  }, [completedCrop, imageSrc, onCropComplete])

  const handleClose = useCallback(() => {
    setCrop(undefined)
    setCompletedCrop(undefined)
    setPreviewUrl(null)
    onClose()
  }, [onClose])

  const canApply =
    completedCrop && completedCrop.width > 0 && completedCrop.height > 0

  return (
    <DialogRoot
      open={isOpen}
      onOpenChange={(details) => {
        if (!details.open) {
          handleClose()
        }
      }}
      size="full"
    >
      <DialogContent>
        <DialogCloseTrigger />
        <DialogHeader>
          <DialogTitle>Crop Image</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <HStack align="start" gap={6} h="full">
            {/* Crop area */}
            <Box
              flex="2"
              display="flex"
              justifyContent="center"
              alignItems="start"
            >
              <ReactCrop
                crop={crop}
                onChange={(c) => setCrop(c)}
                onComplete={handleCropComplete}
              >
                <img
                  ref={imgRef}
                  src={imageSrc}
                  alt="Crop selection area"
                  style={{ maxHeight: "70vh", maxWidth: "100%" }}
                />
              </ReactCrop>
            </Box>

            {/* Preview and controls */}
            <Stack gap={4} minW="300px" maxW="400px">
              <Text fontWeight="bold" fontSize="sm">
                Preview
              </Text>
              <Box
                borderWidth="1px"
                borderRadius="md"
                p={2}
                minH="200px"
                display="flex"
                alignItems="center"
                justifyContent="center"
                bg="rgba(0,0,0,0.1)"
              >
                {previewUrl ? (
                  <Image
                    src={previewUrl}
                    alt="Crop preview"
                    maxH="300px"
                    maxW="100%"
                    objectFit="contain"
                  />
                ) : (
                  <Text color="fg.muted" fontSize="sm">
                    Draw a crop selection on the image
                  </Text>
                )}
              </Box>

              <Text fontSize="xs" color="fg.muted">
                Click and drag on the image to select the area you want to keep.
                The cropped image will replace the original.
              </Text>

              <HStack gap={3} mt={4}>
                <Button
                  variant="outline"
                  onClick={handleClose}
                  disabled={isApplying}
                  flex="1"
                >
                  Cancel
                </Button>
                <Button
                  colorPalette="purple"
                  onClick={handleApply}
                  disabled={!canApply || isApplying}
                  loading={isApplying}
                  loadingText="Applying"
                  flex="1"
                >
                  Apply Crop
                </Button>
              </HStack>
            </Stack>
          </HStack>
        </DialogBody>
      </DialogContent>
    </DialogRoot>
  )
}

export default CropModal
