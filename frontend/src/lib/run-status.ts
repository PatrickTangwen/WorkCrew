import type { RunStatus } from "@/lib/api"

/** How a run's status reads in the sidebar. Colour is carried by the pipeline. */
const runStatusLabels: Record<RunStatus, string> = {
  running: "Running",
  paused: "Paused",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
}

export { runStatusLabels }
