export type PickMode = "directory" | "file"

export type RunStatus = "running" | "paused" | "completed" | "failed" | "cancelled"

export type RunSummary = {
  run_id: string
  status: RunStatus
  started_at: string
  duration: number
  source_name: string
  workbook_name: string
}

export type RunRecord = {
  run_id: string
  status: RunStatus
  start_time: string
  workspace_path: string
  phase: string
  source_name: string
  workbook_name: string
}

type EventBase = {
  timestamp: string
}

export type WorkflowEvent =
  | (EventBase & {
      type: "progress"
      phase: string
      message: string
    })
  | (EventBase & {
      type: "phase_change"
      phase: string
      status: "active" | "completed" | "failed"
    })
  | (EventBase & {
      type: "paused"
      reason: string
      questions_artifact: string
    })
  | (EventBase & {
      type: "completed"
      final_xlsx: string
    })
  | (EventBase & {
      type: "failed"
      error: string
      reason?: "cancelled"
    })

export type ScopingQuestionType =
  | "text"
  | "single_select"
  | "multi_select"
  | "confirm"

export type ScopingQuestion = {
  id: string
  question: string
  type?: ScopingQuestionType
  options?: { value: string; label: string }[] | null
}

export type ScopingAnswerValue = string | string[] | boolean

/** The chosen value, plus whatever the operator wanted to add beside it. */
export type ScopingAnswer = {
  value: ScopingAnswerValue
  note?: string | null
}

export type ScopingAnswers = Record<string, ScopingAnswer>
export type ScopingQuestions = { round: number; questions: ScopingQuestion[] }

export type ArtifactType = "html" | "md" | "xlsx" | "json"

export type ArtifactSummary = {
  name: string
  type: ArtifactType
  size: number
  path: string
}

export type RulesMode = "none" | "text" | "file"

export type CreateRunInput = {
  source: string
  workbook: string
  task: string
  rules_text: string | null
  rules_file: string | null
  scoping_answers: string | null
  review_policy: string | null
}

async function responseError(response: Response) {
  const body = (await response.json()) as { detail?: string }
  return new Error(body.detail ?? `Request failed with status ${response.status}`)
}

async function readResponse<T>(response: Response) {
  if (response.ok) return (await response.json()) as T
  throw await responseError(response)
}

/** Opens the host's native chooser; resolves to null when the operator cancels it. */
export async function pickPath(mode: PickMode, prompt: string) {
  const response = await fetch("/api/pick", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, prompt }),
  })
  const { path } = await readResponse<{ path: string | null }>(response)
  return path
}

export async function createRun(input: CreateRunInput) {
  const response = await fetch("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  })
  return readResponse<RunRecord>(response)
}

export async function listRuns() {
  const response = await fetch("/api/runs")
  return readResponse<RunSummary[]>(response)
}

export async function getRun(runId: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`)
  return readResponse<RunRecord>(response)
}

export function artifactUrl(runId: string, name: string) {
  return `/api/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`
}

export async function listArtifacts(runId: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/artifacts`)
  return readResponse<ArtifactSummary[]>(response)
}

export async function readArtifactText(runId: string, name: string) {
  const response = await fetch(artifactUrl(runId, name))
  if (response.ok) return response.text()
  throw await responseError(response)
}

export async function getScopingQuestions(runId: string) {
  const response = await fetch(artifactUrl(runId, "scoping_questions.json"))
  return readResponse<ScopingQuestions>(response)
}

export async function resumeRun(runId: string, answers: ScopingAnswers) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  })
  return readResponse<RunRecord>(response)
}

export async function cancelRun(runId: string) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, {
    method: "POST",
  })
  return readResponse<RunRecord>(response)
}
