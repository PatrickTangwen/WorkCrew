import { create } from "zustand"

type AppStatus = "starting" | "ready"

type AppState = {
  status: AppStatus
}

export const useAppStore = create<AppState>(() => ({
  status: "ready",
}))
