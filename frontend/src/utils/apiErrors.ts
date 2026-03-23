import { ApiError } from "@/client"

type ValidationErrorItem = {
  msg?: unknown
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null

export function getErrorMessageFromBody(
  body: unknown,
  fallback = "Something went wrong.",
): string {
  if (!isRecord(body)) {
    return fallback
  }

  const detail = body.detail

  if (typeof detail === "string" && detail.trim()) {
    return detail
  }

  if (isRecord(detail)) {
    const message = detail.message
    if (typeof message === "string" && message.trim()) {
      return message
    }
  }

  if (Array.isArray(detail)) {
    const first = detail[0] as ValidationErrorItem | undefined
    if (first && typeof first.msg === "string" && first.msg.trim()) {
      return first.msg
    }
  }

  return fallback
}

export function getDisplayErrorMessage(
  error: unknown,
  fallback = "Something went wrong.",
): string {
  if (error instanceof ApiError) {
    return getErrorMessageFromBody(error.body, fallback)
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message
  }
  return fallback
}

export function getPipelineRunFailureMessage(
  run: {
    error?: { message?: string | null } | null
    error_message?: string | null
  },
  fallback = "Pipeline run failed.",
): string {
  const structured = run.error?.message?.trim()
  if (structured) {
    return structured
  }
  const legacy = run.error_message?.trim()
  if (legacy) {
    return legacy
  }
  return fallback
}
