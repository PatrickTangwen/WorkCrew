import { create } from "zustand"

import type { RunRecord, RunSummary, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

type AppView = "empty" | "new-run" | "run"

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
  openNewRun: () => void
  showRun: (run: RunRecord) => void
  startHistoryLoad: () => void
  receiveRuns: (runs: RunSummary[]) => void
  failHistoryLoad: (message: string) => void
  connectRunStream: (runId: string) => void
  disconnectRunStream: () => void
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

export const useAppStore = create<AppState>()((set) => ({
  view: "empty",
  currentRun: null,
  runs: [],
  historyStatus: "idle",
  historyError: null,
  streamRunId: null,
  streamEvents: [],
  streamStatus: "idle",
  streamError: null,
  openNewRun: () => set({ view: "new-run" }),
  showRun: (run) =>
    set((state) => {
      return {
        view: "run",
        currentRun: run,
        runs: withRunSummary(state.runs, run),
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
}))
