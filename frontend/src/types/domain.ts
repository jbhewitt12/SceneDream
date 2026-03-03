export type DocumentIngestionState =
  | "pending"
  | "ingested"
  | "failed"
  | "processing"

export interface Document {
  id: string
  slug: string
  displayName: string | null
  sourcePath: string
  sourceType: string
  ingestionState: DocumentIngestionState
  ingestionError: string | null
  sourceMetadata: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

export interface PipelineRun {
  id: string
  documentId: string | null
  bookSlug: string | null
  status: string
  currentStage: string | null
  errorMessage: string | null
  configOverrides: Record<string, unknown>
  startedAt: string | null
  completedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface GeneratedAsset {
  id: string
  documentId: string | null
  pipelineRunId: string | null
  sceneExtractionId: string | null
  imagePromptId: string | null
  assetType: string
  status: string
  provider: string | null
  model: string | null
  storagePath: string | null
  fileName: string | null
  mimeType: string | null
  assetMetadata: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

type LegacySceneSummary = {
  id: string
  book_slug: string
  source_book_path: string
}

export const mapLegacySceneToDocument = (
  scene: LegacySceneSummary,
): Omit<Document, "createdAt" | "updatedAt"> => ({
  id: scene.id,
  slug: scene.book_slug,
  displayName: null,
  sourcePath: scene.source_book_path,
  sourceType: scene.source_book_path.split(".").pop() ?? "epub",
  ingestionState: "ingested",
  ingestionError: null,
  sourceMetadata: { legacyBookSlug: scene.book_slug },
})
