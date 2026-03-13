import {
  type PipelineRunRead,
  type PipelineRunStartRequest,
  PipelineRunsService,
} from "@/client"

export type PipelineRun = PipelineRunRead

export const PipelineRunsApi = {
  async start(payload: PipelineRunStartRequest): Promise<PipelineRun> {
    return (await PipelineRunsService.startPipelineRun({
      requestBody: payload,
    })) as PipelineRun
  },

  async get(runId: string): Promise<PipelineRun> {
    return (await PipelineRunsService.getPipelineRun({
      runId,
    })) as PipelineRun
  },
}
