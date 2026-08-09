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

export type RunRecord = {
  run_id: string
  status: "running" | "paused" | "completed" | "failed"
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
