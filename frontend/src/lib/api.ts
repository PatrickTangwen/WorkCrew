export type BrowseEntry = {
  name: string
  type: "directory" | "file"
  size: number
  modified: string
}

export type BrowseListing = {
  path: string
  root: string
  entries: BrowseEntry[]
}

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

export type CreateRunInput = {
  source: string
  workbook: string
  rules: string
  workbook_schema: string
  scoping_answers: string | null
  review_policy: string | null
}

async function readResponse<T>(response: Response) {
  if (response.ok) {
    return (await response.json()) as T
  }

  const body = (await response.json()) as { detail?: string }
  throw new Error(body.detail ?? `Request failed with status ${response.status}`)
}

export async function browseFiles(path?: string) {
  const search = path ? `?${new URLSearchParams({ path })}` : ""
  const response = await fetch(`/api/browse${search}`)
  return readResponse<BrowseListing>(response)
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
