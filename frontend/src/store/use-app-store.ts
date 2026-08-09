import { create } from "zustand"

import type { RunRecord, RunSummary } from "@/lib/api"

type AppView = "empty" | "new-run" | "run"

type AppState = {
  view: AppView
  currentRun: RunRecord | null
  runs: RunSummary[]
  historyStatus: "idle" | "loading" | "ready" | "error"
  historyError: string | null
  openNewRun: () => void
  showRun: (run: RunRecord) => void
  startHistoryLoad: () => void
  receiveRuns: (runs: RunSummary[]) => void
  failHistoryLoad: (message: string) => void
}

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

export const useAppStore = create<AppState>((set) => ({
  view: "empty",
  currentRun: null,
  runs: [],
  historyStatus: "idle",
  historyError: null,
  openNewRun: () => set({ view: "new-run" }),
  showRun: (run) =>
    set((state) => {
      const existing = state.runs.find((item) => item.run_id === run.run_id)
      return {
        view: "run",
        currentRun: run,
        runs: newestFirst([
          summaryOf(run, existing?.duration),
          ...state.runs.filter((item) => item.run_id !== run.run_id),
        ]),
      }
    }),
  startHistoryLoad: () => set({ historyStatus: "loading", historyError: null }),
  receiveRuns: (runs) =>
    set((state) => {
      if (!state.currentRun) {
        return { runs: newestFirst(runs), historyStatus: "ready" }
      }
      return {
        runs: newestFirst([
          summaryOf(
            state.currentRun,
            runs.find((item) => item.run_id === state.currentRun?.run_id)?.duration
          ),
          ...runs.filter((item) => item.run_id !== state.currentRun?.run_id),
        ]),
        historyStatus: "ready",
      }
    }),
  failHistoryLoad: (message) =>
    set({ historyStatus: "error", historyError: message }),
}))
