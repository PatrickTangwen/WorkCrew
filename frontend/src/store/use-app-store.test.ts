import { beforeEach, expect, it, vi } from "vitest"

import type { RunRecord } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

const apiMocks = vi.hoisted(() => ({
  cancelRun: vi.fn(),
  resumeRun: vi.fn(),
}))

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  cancelRun: apiMocks.cancelRun,
  resumeRun: apiMocks.resumeRun,
}))

const pausedRun: RunRecord = {
  run_id: "run-paused",
  status: "paused",
  start_time: "2026-08-09T12:00:00Z",
  workspace_path: "/runs/run-paused",
  phase: "CLAUDE_SCOPE",
  source_name: "source-a",
  workbook_name: "template-a.xlsx",
}

const otherRun: RunRecord = {
  ...pausedRun,
  run_id: "run-other",
  status: "completed",
  phase: "FINALIZE",
  source_name: "source-b",
  workbook_name: "template-b.xlsx",
}

beforeEach(() => {
  useAppStore.getState().disconnectRunStream()
  useAppStore.setState(useAppStore.getInitialState())
  apiMocks.resumeRun.mockReset()
  apiMocks.cancelRun.mockReset()
})

it("applies cancellation to the selected detail and its sidebar summary", async () => {
  const running = { ...pausedRun, status: "running" as const }
  apiMocks.cancelRun.mockResolvedValue({ ...running, status: "cancelled" })
  useAppStore.getState().showRun(running)

  await useAppStore.getState().cancelRun(running.run_id)

  expect(useAppStore.getState().currentRun?.status).toBe("cancelled")
  expect(useAppStore.getState().runs[0].status).toBe("cancelled")
})

it("applies retry to a terminal detail and its sidebar summary", async () => {
  const failed = { ...pausedRun, status: "failed" as const }
  apiMocks.resumeRun.mockResolvedValue({ ...failed, status: "running" })
  useAppStore.getState().showRun(failed)
  useAppStore.setState({
    streamRunId: failed.run_id,
    streamEvents: [
      {
        type: "failed",
        timestamp: "2026-08-09T12:01:00Z",
        error: "Temporary failure",
      },
    ],
  })

  await useAppStore.getState().retryRun(failed.run_id)

  expect(apiMocks.resumeRun).toHaveBeenCalledWith(failed.run_id, {})
  expect(useAppStore.getState().currentRun?.status).toBe("running")
  expect(useAppStore.getState().runs[0].status).toBe("running")
  expect(useAppStore.getState().streamRunId).toBeNull()
  expect(useAppStore.getState().streamEvents).toEqual([])
})

it("does not apply a stale resume result after another run is selected", async () => {
  let finishResume: ((run: RunRecord) => void) | undefined
  apiMocks.resumeRun.mockReturnValue(
    new Promise<RunRecord>((resolve) => {
      finishResume = resolve
    })
  )
  useAppStore.getState().showRun(pausedRun)
  useAppStore.setState({
    scoping: {
      runId: pausedRun.run_id,
      questions: [],
      status: "ready",
      error: null,
    },
  })

  const pending = useAppStore
    .getState()
    .resumeRun(pausedRun.run_id, { Q1: "One source file." })
  useAppStore.getState().showRun(otherRun)
  finishResume?.({ ...pausedRun, status: "running" })
  await pending

  const state = useAppStore.getState()
  expect(state.currentRun).toEqual(otherRun)
  expect(state.runs.find((run) => run.run_id === pausedRun.run_id)?.status).toBe(
    "running"
  )
  expect(state.scoping.runId).toBeNull()
  expect(state.scoping.status).toBe("idle")
})

it("does not apply a stale resume error after another run is selected", async () => {
  let failResume: ((cause: Error) => void) | undefined
  apiMocks.resumeRun.mockReturnValue(
    new Promise<RunRecord>((_resolve, reject) => {
      failResume = reject
    })
  )
  useAppStore.getState().showRun(pausedRun)
  useAppStore.setState({
    scoping: {
      runId: pausedRun.run_id,
      questions: [],
      status: "ready",
      error: null,
    },
  })

  const pending = useAppStore
    .getState()
    .resumeRun(pausedRun.run_id, { Q1: "One source file." })
  useAppStore.getState().showRun(otherRun)
  failResume?.(new Error("Resume failed"))
  await pending

  const state = useAppStore.getState()
  expect(state.currentRun).toEqual(otherRun)
  expect(state.scoping.runId).toBeNull()
  expect(state.scoping.status).toBe("idle")
  expect(state.scoping.error).toBeNull()
})
