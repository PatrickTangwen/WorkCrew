import type { RunRecord, RunStatus, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

// Re-review is folded into Finalize: it is the same closing pass from the
// operator's side, and split out it left a card that rarely had anything of
// its own to report.
const STAGES = ["Scoping", "Filler", "Review", "Revision", "Finalize"]

const phaseStage: Record<string, number> = {
  INITIALIZING: 0,
  INIT: 0,
  PREPARE_WORKSPACE: 0,
  BUILD_MANIFEST: 0,
  OUTLINE_WORKBOOK: 0,
  LOAD_SCHEMA: 0,
  CLAUDE_SCOPE: 0,
  AWAIT_SCOPING_ANSWERS: 0,
  CLAUDE_FILL: 1,
  VALIDATE: 1,
  WRITE_DRAFT: 1,
  CODEX_REVIEW: 2,
  CLAUDE_REVISE: 3,
  APPLY_ALLOWED_REVISIONS: 3,
  CODEX_REREVIEW: 4,
  HUMAN_REVIEW: 4,
  FINALIZE: 4,
}

type StageState =
  | "completed"
  | "active"
  | "waiting"
  | "failed"
  | "stopped"
  | "pending"

type StageEntry = {
  timestamp: string
  message: string
  failed: boolean
}

type StageView = {
  name: string
  state: StageState
  /** Seconds spent in the stage, or null when no event placed the run there. */
  duration: number | null
  entries: StageEntry[]
}

type PipelineView = {
  stages: StageView[]
  /** The stage the run sits on; past the last once all of them are behind it. */
  current: number
  status: RunStatus
  /** When the run stopped, or null while it is still on the clock. */
  finishedAt: string | null
  /** The newest unrecoverable error, which is what stopped the run. */
  failure: string | null
}

const terminalStatuses: RunStatus[] = ["completed", "failed", "cancelled"]

/**
 * The stream is fresher than the record, but only about endings: a reopened
 * run knows its own status, and a resumed one has already left the pause the
 * events still remember.
 */
/**
 * What the run is doing, and when it stopped if it has. The engine narrates
 * in order, so its last word is the current state: a pause or a failure that
 * was followed by more work is history, not status. The record answers only
 * for a run that has nothing recorded.
 */
function endingOf(run: RunRecord, events: WorkflowEvent[]) {
  const last = events[events.length - 1]
  if (last === undefined) return { status: run.status, at: run.finished_at }
  const status = workflowEventDetails(last).runStatus
  if (status === null) return { status: "running" as RunStatus, at: null }
  // A terminal event is the moment the run stopped, which is what the clock
  // settles on without waiting for a reload.
  return { status, at: terminalStatuses.includes(status) ? last.timestamp : null }
}

function stageStates(
  current: number,
  outcome: RunStatus,
  phaseStatus: "active" | "completed" | "failed" | null
) {
  return STAGES.map((_, index): StageState => {
    if (index < current) return "completed"
    if (index > current) return "pending"
    if (outcome === "completed") return "completed"
    if (outcome === "failed" || phaseStatus === "failed") return "failed"
    if (outcome === "cancelled") return "stopped"
    if (outcome === "paused") return "waiting"
    return phaseStatus === "completed" ? "completed" : "active"
  })
}

function pipelineView(run: RunRecord, events: WorkflowEvent[]): PipelineView {
  const ending = endingOf(run, events)
  const outcome = ending.status
  const details = events.map(workflowEventDetails)

  const lastPhaseChange = [...details]
    .reverse()
    .find((detail) => detail.phaseStatus !== null)
  const phase = lastPhaseChange?.phase ?? run.phase
  const current =
    outcome === "completed" ? STAGES.length : (phaseStage[phase] ?? 0)

  const elapsed = STAGES.map(() => 0)
  const visited = STAGES.map(() => false)
  const entries: StageEntry[][] = STAGES.map(() => [])
  let previous: { stage: number; at: number } | null = null
  let here = 0

  for (const [index, detail] of details.entries()) {
    const stage = detail.phase === null ? here : (phaseStage[detail.phase] ?? here)
    here = stage
    entries[stage].push({
      timestamp: events[index].timestamp,
      message: detail.logMessage,
      failed: detail.error !== null || detail.phaseStatus === "failed",
    })

    const at = Date.parse(events[index].timestamp)
    if (Number.isNaN(at)) continue
    if (previous !== null) elapsed[previous.stage] += Math.max(0, at - previous.at)
    visited[stage] = true
    previous = { stage, at }
  }

  // A run still on the clock keeps accruing time in the stage it is in.
  if (previous !== null && (outcome === "running" || outcome === "paused")) {
    elapsed[previous.stage] += Math.max(0, Date.now() - previous.at)
  }

  const states = stageStates(current, outcome, lastPhaseChange?.phaseStatus ?? null)
  const failure =
    [...details].reverse().find((detail) => detail.error !== null)?.error ?? null

  return {
    stages: STAGES.map((name, index) => ({
      name,
      state: states[index],
      duration: visited[index] ? elapsed[index] / 1000 : null,
      entries: entries[index],
    })),
    current,
    status: outcome,
    finishedAt: ending.at,
    failure,
  }
}

/** The word and ink each stage state wears in the pipeline card. */
const stageStatePresentation: Record<
  StageState,
  { word: string; className: string }
> = {
  completed: { word: "Done", className: "text-body" },
  active: { word: "Running", className: "text-brand" },
  waiting: { word: "Waiting", className: "text-brand-ink" },
  failed: { word: "Failed", className: "text-bad-ink" },
  stopped: { word: "Stopped", className: "text-subtle" },
  pending: { word: "Pending", className: "text-ghost" },
}

/** What a stage says about itself when it has no events to show. */
const stageSummary: Record<StageState, string> = {
  completed: "Completed without open items.",
  active: "In progress now — events stream in below.",
  waiting: "Blocked on operator input before it can finish.",
  failed: "Stopped here. Nothing after this stage ran.",
  stopped: "Interrupted by the operator.",
  pending: "Not started. Runs once the stages before it finish.",
}

export {
  phaseStage,
  pipelineView,
  STAGES,
  stageStatePresentation,
  stageSummary,
  type PipelineView,
  type StageEntry,
  type StageState,
  type StageView,
}
