import { OpenAPI } from "@/client"

type TriggerForBookParams = {
  bookSlug: string
  promptVersion?: string | null
  modelName?: string | null
}

type TriggerForSceneParams = {
  sceneId: string
  promptVersion?: string | null
  modelName?: string | null
}

const buildUrl = (path: string) => {
  const base = OpenAPI.BASE ?? ""
  if (base?.endsWith("/")) {
    return `${base.replace(/\/+$/, "")}${path}`
  }
  return `${base}${path}`
}

const postJson = async (url: string, payload: Record<string, unknown>) => {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const errorBody = await response.text().catch(() => "")
    throw new Error(
      errorBody ||
        `${response.status} ${response.statusText}` ||
        "Request failed",
    )
  }

  if (response.status === 204) {
    return null
  }

  try {
    return await response.json()
  } catch (error) {
    if (error instanceof SyntaxError) {
      return null
    }
    throw error
  }
}

export const ImagePromptGenerationApi = {
  triggerForBook({ bookSlug, promptVersion, modelName }: TriggerForBookParams) {
    const url = buildUrl(
      `/api/v1/image-prompt-generation/book/${encodeURIComponent(bookSlug)}`,
    )
    return postJson(url, {
      prompt_version: promptVersion ?? undefined,
      model_name: modelName ?? undefined,
    })
  },

  triggerForScene({
    sceneId,
    promptVersion,
    modelName,
  }: TriggerForSceneParams) {
    const url = buildUrl(
      `/api/v1/image-prompt-generation/scene/${encodeURIComponent(sceneId)}`,
    )
    return postJson(url, {
      prompt_version: promptVersion ?? undefined,
      model_name: modelName ?? undefined,
    })
  },
}
