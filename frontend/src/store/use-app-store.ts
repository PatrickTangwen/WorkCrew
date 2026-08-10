import { create } from "zustand"

import {
  cancelRun as requestRunCancel,
  getScopingQuestions,
  resumeRun as requestRunResume,
  type RunRecord,
  type RunSummary,
  type ScopingAnswers,
  type ScopingQuestion,
  type WorkflowEvent,
} from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

type AppView = "empty" | "new-run" | "run"
type ScopingStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type ScopingState = {
  runId: string | null
  questions: ScopingQuestion[]
  status: ScopingStatus
  error: string | null
}

type RunActionState = {
  runId: string | null
  kind: "cancel" | "retry" | null
  status: "idle" | "submitting" | "error"
  error: string | null
}

type AppState = {
  view: AppView
  currentRun: RunRecord | null
  runs: RunSummary[]
  historyStatus: "idle" | "loading" | "ready" | "error"
  historyError: string | null
  streamRunId: string | null
  streamEvents: WorkflowEvent[]
  streamStatus: "idle" | "connecting" | "connected" | "disconnected" | "error"
  streamError: string | null
  scoping: ScopingState
  runAction: RunActionState
  openNewRun: () => void
  showRun: (run: RunRecord) => void
  startHistoryLoad: () => void
  receiveRuns: (runs: RunSummary[]) => void
  failHistoryLoad: (message: string) => void
  connectRunStream: (runId: string) => void
  disconnectRunStream: () => void
  loadScopingQuestions: (runId: string) => Promise<void>
  resumeRun: (runId: string, answers: ScopingAnswers) => Promise<void>
  cancelRun: (runId: string) => Promise<void>
  retryRun: (runId: string) => Promise<void>
}

let activeSocket: WebSocket | null = null

function summaryOf(run: RunRecord, duration = 0): RunSummary {
  return {
    run_id: run.run_id,
    status: run.status,
    started_at: run.start_time,
    duration,
    source_name: run.source_name,
    workbook_name: run.workbook_name,
  }
}

function newestFirst(runs: RunSummary[]) {
  return [...runs].sort((left, right) =>
    right.started_at.localeCompare(left.started_at)
  )
}

function withRunSummary(runs: RunSummary[], run: RunRecord) {
  const existing = runs.find((item) => item.run_id === run.run_id)
  return newestFirst([
    summaryOf(run, existing?.duration),
    ...runs.filter((item) => item.run_id !== run.run_id),
  ])
}

function websocketUrl(runId: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runs/${encodeURIComponent(runId)}`
}

function runAfterEvent(run: RunRecord, event: WorkflowEvent) {
  const details = workflowEventDetails(event)
  return {
    ...run,
    phase: details.phase ?? run.phase,
    status: details.runStatus ?? run.status,
  }
}

function runAfterResume(current: RunRecord | null, resumed: RunRecord) {
  if (current?.run_id !== resumed.run_id) return current
  if (["completed", "failed", "cancelled"].includes(current.status)) return current
  return { ...resumed, phase: current.phase }
}

function emptyScopingState(): ScopingState {
  return { runId: null, questions: [], status: "idle", error: null }
}

function emptyRunActionState(): RunActionState {
  return { runId: null, kind: null, status: "idle", error: null }
}

function runAfterAction(current: RunRecord | null, run: RunRecord) {
  return current?.run_id === run.run_id ? run : current
}

function scopingStateForRun(scoping: ScopingState, runId: string) {
  return scoping.runId === runId ? scoping : emptyScopingState()
}

export const useAppStore = create<AppState>()((set, get) => ({
  view: "empty",
  currentRun: null,
  runs: [],
  historyStatus: "idle",
  historyError: null,
  streamRunId: null,
  streamEvents: [],
  streamStatus: "idle",
  streamError: null,
  scoping: emptyScopingState(),
  runAction: emptyRunActionState(),
  openNewRun: () => set({ view: "new-run" }),
  showRun: (run) =>
    set((state) => {
      return {
        view: "run",
        currentRun: run,
        runs: withRunSummary(state.runs, run),
        scoping: scopingStateForRun(state.scoping, run.run_id),
      }
    }),
  startHistoryLoad: () => set({ historyStatus: "loading", historyError: null }),
  receiveRuns: (runs) =>
    set((state) => {
      if (!state.currentRun) {
        return { runs: newestFirst(runs), historyStatus: "ready" }
      }
      return {
        runs: withRunSummary(runs, state.currentRun),
        historyStatus: "ready",
      }
    }),
  failHistoryLoad: (message) =>
    set({ historyStatus: "error", historyError: message }),
  connectRunStream: (runId) => {
    if (activeSocket !== null) {
      const previous = activeSocket
      activeSocket = null
      previous.close()
    }

    set((state) => ({
      streamRunId: runId,
      streamEvents: state.streamRunId === runId ? state.streamEvents : [],
      streamStatus: "connecting",
      streamError: null,
      scoping: scopingStateForRun(state.scoping, runId),
    }))
    const socket = new WebSocket(websocketUrl(runId))
    activeSocket = socket

    socket.onopen = () => {
      if (activeSocket === socket) set({ streamStatus: "connected" })
    }
    socket.onmessage = (message) => {
      if (activeSocket !== socket) return
      let event: WorkflowEvent
      try {
        event = JSON.parse(message.data) as WorkflowEvent
      } catch {
        set({
          streamStatus: "error",
          streamError: "The run stream returned invalid JSON",
        })
        return
      }

      const details = workflowEventDetails(event)

      set((state) => {
        if (state.streamRunId !== runId) return state
        const currentRun =
          state.currentRun?.run_id === runId
            ? runAfterEvent(state.currentRun, event)
            : state.currentRun
        return {
          streamEvents: [...state.streamEvents, event],
          currentRun,
          runs: currentRun ? withRunSummary(state.runs, currentRun) : state.runs,
        }
      })
      if (details.runStatus === "paused") {
        void get().loadScopingQuestions(runId)
      }
    }
    socket.onerror = () => {
      if (activeSocket === socket) {
        set({ streamStatus: "error", streamError: "Run stream connection failed" })
      }
    }
    socket.onclose = () => {
      if (activeSocket === socket) {
        activeSocket = null
        set((state) => ({
          streamStatus: state.streamStatus === "error" ? "error" : "disconnected",
        }))
      }
    }
  },
  disconnectRunStream: () => {
    if (activeSocket !== null) {
      const socket = activeSocket
      activeSocket = null
      socket.close()
    }
    set({ streamStatus: "idle" })
  },
  loadScopingQuestions: async (runId) => {
    const current = get()
    if (
      current.scoping.runId === runId &&
      (current.scoping.status === "loading" || current.scoping.status === "ready")
    ) {
      return
    }
    set({
      scoping: { runId, questions: [], status: "loading", error: null },
    })
    try {
      const response = await getScopingQuestions(runId)
      if (get().scoping.runId === runId) {
        set((state) => ({
          scoping: {
            ...state.scoping,
            questions: response.questions,
            status: "ready",
          },
        }))
      }
    } catch (cause) {
      if (get().scoping.runId === runId) {
        set((state) => ({
          scoping: {
            ...state.scoping,
            status: "error",
            error:
              cause instanceof Error
                ? cause.message
                : "Unable to load scoping questions",
          },
        }))
      }
    }
  },
  resumeRun: async (runId, answers) => {
    if (get().scoping.runId !== runId) return
    set((state) => ({
      scoping: { ...state.scoping, status: "submitting", error: null },
    }))
    try {
      const run = await requestRunResume(runId, answers)
      set((state) => {
        const currentRun = runAfterResume(state.currentRun, run)
        const summaryRun = currentRun?.run_id === runId ? currentRun : run
        const currentScoping = state.scoping.runId === runId
        return {
          currentRun,
          runs: withRunSummary(state.runs, summaryRun),
          ...(currentScoping
            ? { scoping: { ...state.scoping, status: "ready" as const } }
            : {}),
        }
      })
    } catch (cause) {
      set((state) =>
        state.scoping.runId === runId
          ? {
              scoping: {
                ...state.scoping,
                status: "error",
                error:
                  cause instanceof Error
                    ? cause.message
                    : "Unable to resume the run",
              },
            }
          : {}
      )
    }
  },
  cancelRun: async (runId) => {
    set({
      runAction: { runId, kind: "cancel", status: "submitting", error: null },
    })
    try {
      const run = await requestRunCancel(runId)
      set((state) => ({
        currentRun: runAfterAction(state.currentRun, run),
        runs: withRunSummary(state.runs, run),
        runAction: emptyRunActionState(),
      }))
    } catch (cause) {
      set((state) =>
        state.runAction.runId === runId
          ? {
              runAction: {
                runId,
                kind: "cancel",
                status: "error",
                error:
                  cause instanceof Error ? cause.message : "Unable to cancel the run",
              },
            }
          : {}
      )
    }
  },
  retryRun: async (runId) => {
    set({
      runAction: { runId, kind: "retry", status: "submitting", error: null },
    })
    try {
      const run = await requestRunResume(runId, {})
      set((state) => {
        const selected = state.currentRun?.run_id === runId
        return {
          currentRun: runAfterAction(state.currentRun, run),
          runs: withRunSummary(state.runs, run),
          runAction: emptyRunActionState(),
          ...(selected
            ? {
                streamRunId: null,
                streamEvents: [],
                streamStatus: "idle" as const,
                streamError: null,
              }
            : {}),
        }
      })
    } catch (cause) {
      set((state) =>
        state.runAction.runId === runId
          ? {
              runAction: {
                runId,
                kind: "retry",
                status: "error",
                error: cause instanceof Error ? cause.message : "Unable to retry the run",
              },
            }
          : {}
      )
    }
  },
}))
