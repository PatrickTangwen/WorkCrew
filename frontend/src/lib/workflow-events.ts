import type { RunStatus, WorkflowEvent } from "@/lib/api"

type PhaseStatus = "active" | "completed" | "failed"

type WorkflowEventDetails = {
  phase: string | null
  phaseStatus: PhaseStatus | null
  runStatus: RunStatus | null
  logMessage: string
  error: string | null
}

function workflowEventDetails(event: WorkflowEvent): WorkflowEventDetails {
  if (event.type === "progress") {
    return {
      phase: event.phase,
      phaseStatus: null,
      runStatus: null,
      logMessage: event.message,
      error: null,
    }
  }
  if (event.type === "phase_change") {
    return {
      phase: event.phase,
      phaseStatus: event.status,
      runStatus: null,
      logMessage: `${event.phase} ${event.status === "active" ? "started" : event.status}`,
      error: null,
    }
  }
  if (event.type === "paused") {
    return {
      phase: null,
      phaseStatus: null,
      runStatus: "paused",
      logMessage: event.reason,
      error: null,
    }
  }
  if (event.type === "completed") {
    return {
      phase: "FINALIZE",
      phaseStatus: null,
      runStatus: "completed",
      logMessage: `Run completed: ${event.final_xlsx}`,
      error: null,
    }
  }
  if (event.reason === "cancelled") {
    return {
      phase: null,
      phaseStatus: null,
      runStatus: "cancelled",
      logMessage: event.error,
      error: null,
    }
  }
  return {
    phase: null,
    phaseStatus: null,
    runStatus: "failed",
    logMessage: event.error,
    error: event.error,
  }
}

export { workflowEventDetails }
