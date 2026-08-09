import { create } from "zustand"

import type { RunRecord } from "@/lib/api"

type AppView = "empty" | "new-run" | "run"

type AppState = {
  view: AppView
  currentRun: RunRecord | null
  openNewRun: () => void
  showRun: (run: RunRecord) => void
}

export const useAppStore = create<AppState>(() => ({
  view: "empty",
  currentRun: null,
  openNewRun: () => useAppStore.setState({ view: "new-run" }),
  showRun: (run) => useAppStore.setState({ view: "run", currentRun: run }),
}))
