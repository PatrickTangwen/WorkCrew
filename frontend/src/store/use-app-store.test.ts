import { beforeEach, expect, it, vi } from "vitest"

import type { RunRecord } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

const apiMocks = vi.hoisted(() => ({
  resumeRun: vi.fn(),
}))

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
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
