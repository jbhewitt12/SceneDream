import { OpenAPI } from "@/client"

const trimSlashes = (value: string) => value.replace(/^\/+|\/+$/g, "")

const resolveOrigin = (): string => {
  if (typeof window !== "undefined") {
    return window.location.origin
  }
  return ""
}

type BuildUrlArgs = {
  id: string
  storagePath: string
  fileName: string
}

export const buildGeneratedImageUrl = ({
  id,
  storagePath,
  fileName,
}: BuildUrlArgs): string => {
  const base = OpenAPI.BASE?.trim()
  if (base) {
    try {
      return new URL(`/api/v1/generated-images/${id}/content`, base).toString()
    } catch {
      const sanitizedBase = base.replace(/\/+$/, "")
      return `${sanitizedBase}/api/v1/generated-images/${id}/content`
    }
  }

  const origin = resolveOrigin()
  const path = [storagePath, fileName]
    .map((segment) => trimSlashes(segment))
    .filter(Boolean)
    .join("/")

  if (!path) {
    return origin || "/"
  }

  if (!origin) {
    return `/${path}`
  }

  return `${origin}/${path}`
}
