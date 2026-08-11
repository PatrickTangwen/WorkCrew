
# WorkCrew — Full Frontend Component Reference for Redesign

WorkCrew is a **local-first document-to-workbook workflow desk**. An operator picks a folder of source documents, an Excel workbook template, a rules folder, and a JSON schema; the backend then runs a multi-stage agent pipeline (Scoping → Filler → Review → Revision → Re-review → Finalize) that fills the workbook and produces auditable artifacts. The UI is served by a local Python server on loopback and opened in the operator's own browser — there is no cloud, no login, no multi-user state.

**Tech stack**: React 19, TypeScript, Vite 8, Tailwind CSS v4 (`@theme inline`, no config file), shadcn/ui (`radix-nova` style, only Badge/Button/Card vendored), Radix UI primitives, lucide-react icons, Zustand 5, react-markdown, Geist Variable font.

**Styling idiom**: utility classes only. There are **no CSS modules and no styled-components** — every component is styled with Tailwind utilities that resolve to the semantic token set defined in `src/index.css`. `cn()` (clsx + tailwind-merge) merges conditional classes. Component variants use `class-variance-authority` (`cva`).

**Visual character**: near-monochrome. The entire chrome is built from `oklch` greys with `--radius: 0.625rem`; the only saturated colors in the app are the five run-status accents (emerald / amber / sky / red / stone) and `--destructive`. Headings use `font-heading` (aliased to Geist), identifiers and paths use `font-mono`. Surfaces are layered by opacity (`bg-muted/18`, `bg-muted/20`, `bg-muted/30`, `bg-muted/35`) rather than by distinct color values.

---

## Page Layout Overview

The app is a single full-height screen with **no router** — `view` state in the Zustand store switches the right pane between three modes.

```
┌───────────────────┬──────────────────────────────────────────────┐
│  RunSidebar       │  <section>  main pane                        │
│  288px fixed      │  p-5 / sm:p-8 / lg:p-10                      │
│  (lg breakpoint)  │                                              │
│                   │  view === "empty"    → centered empty state  │
│  · brand block    │  view === "new-run"  → RunCreationForm       │
│  · New run button │  view === "run"      → RunDetail             │
│  · RUNS list      │                                              │
│  · "Local only"   │                                              │
└───────────────────┴──────────────────────────────────────────────┘
```

- Grid: `lg:grid lg:grid-cols-[288px_minmax(0,1fr)]` on a `min-h-svh` root with `bg-muted/30`.
- **Below `lg` the layout collapses to stacked**: the sidebar becomes a top bar with a *horizontally scrolling, snap-scrolling* run list (`flex snap-x overflow-x-auto`, each card `min-w-64`), and the footer "Local only" badge is hidden in favor of a compact `Local` badge in the header.
- The main pane is always `min-w-0` so long monospace paths truncate instead of blowing out the grid.
- Inner content is width-capped per view: `max-w-4xl` for the creation form, `max-w-5xl` for run detail.

---

## 1. App Shell: `App.tsx`

Owns the two-column grid, loads run history once on mount, and renders one of three views. All view state lives in the Zustand store, not in local state.

```tsx
// frontend/src/App.tsx
import { useEffect } from "react"
import { Files, Plus } from "lucide-react"

import { RunCreationForm } from "@/components/run-creation-form"
import { RunDetail } from "@/components/run-detail"
import { RunSidebar } from "@/components/run-sidebar"
import { Button } from "@/components/ui/button"
import { getRun, listRuns, type RunSummary } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

function App() {
  // Individually-selected store slices: view, currentRun, runs, historyStatus,
  // historyError, openNewRun, showRun, startHistoryLoad, receiveRuns, failHistoryLoad
  const view = useAppStore((state) => state.view)
  const currentRun = useAppStore((state) => state.currentRun)
  const runs = useAppStore((state) => state.runs)
  const historyStatus = useAppStore((state) => state.historyStatus)
  const historyError = useAppStore((state) => state.historyError)
  const openNewRun = useAppStore((state) => state.openNewRun)
  const showRun = useAppStore((state) => state.showRun)
  const startHistoryLoad = useAppStore((state) => state.startHistoryLoad)
  const receiveRuns = useAppStore((state) => state.receiveRuns)
  const failHistoryLoad = useAppStore((state) => state.failHistoryLoad)

  useEffect(() => {
    // Fetches GET /api/runs once on mount, guarded by an `ignore` flag.
    let ignore = false
    startHistoryLoad()
    void listRuns()
      .then((history) => { if (!ignore) receiveRuns(history) })
      .catch((cause: unknown) => {
        if (!ignore) {
          failHistoryLoad(cause instanceof Error ? cause.message : "Unable to load run history")
        }
      })
    return () => { ignore = true }
  }, [failHistoryLoad, receiveRuns, startHistoryLoad])

  async function selectRun(run: RunSummary) {
    try {
      showRun(await getRun(run.run_id))
    } catch (cause) {
      failHistoryLoad(cause instanceof Error ? cause.message : "Unable to open the selected run")
    }
  }

  return (
    <main className="min-h-svh bg-muted/30 lg:grid lg:grid-cols-[288px_minmax(0,1fr)]">
      <RunSidebar
        runs={runs}
        selectedRunId={view === "run" ? (currentRun?.run_id ?? null) : null}
        historyStatus={historyStatus}
        historyError={historyError}
        onNewRun={openNewRun}
        onSelect={(run) => void selectRun(run)}
      />

      <section
        aria-label={view === "run" ? "Run detail" : undefined}
        className="min-w-0 p-5 sm:p-8 lg:p-10"
      >
        {view === "new-run" && <RunCreationForm onCreated={showRun} />}
        {view === "run" && currentRun && <RunDetail run={currentRun} />}
        {view === "empty" && (
          <div className="grid min-h-[calc(100svh-110px)] place-items-center lg:min-h-[calc(100svh-80px)]">
            <div className="max-w-md text-center">
              <div className="mx-auto grid size-14 place-items-center rounded-2xl border bg-background shadow-sm">
                <Files className="size-6" aria-hidden="true" />
              </div>
              <h1 className="mt-5 font-heading text-3xl font-semibold tracking-tight">
                Start with the working set.
              </h1>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                Select source documents, a workbook, and the rules that turn them into a traceable run.
              </p>
              <Button onClick={openNewRun} className="mt-6">
                <Plus /> New run
              </Button>
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
```

---

## 2. Left Rail: `run-sidebar.tsx`

Brand block, the primary "New run" CTA, the run history list, and a persistent "Local only" trust badge. Handles four history states (loading / error / empty / populated).

```tsx
// frontend/src/components/run-sidebar.tsx
import { Clock3, PanelsTopLeft, Plus, ShieldCheck } from "lucide-react"

import { RunStatusBadge } from "@/components/run-status-badge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { RunSummary } from "@/lib/api"
import { cn } from "@/lib/utils"

type RunSidebarProps = {
  runs: RunSummary[]
  selectedRunId: string | null
  historyStatus: "idle" | "loading" | "ready" | "error"
  historyError: string | null
  onNewRun: () => void
  onSelect: (run: RunSummary) => void
}

// formatDuration(seconds) → "42s" | "3m 5s" | "1h 20m"
// formatStartTime(iso)    → Intl.DateTimeFormat(month:"short", day:"numeric", hour:"numeric", minute:"2-digit")

function RunSidebar({ runs, selectedRunId, historyStatus, historyError, onNewRun, onSelect }: RunSidebarProps) {
  return (
    <aside
      aria-label="Run history"
      className="flex min-w-0 flex-col border-b bg-background lg:min-h-svh lg:border-r lg:border-b-0"
    >
      {/* Brand block */}
      <div className="flex items-center gap-3 border-b px-4 py-3 lg:px-5 lg:py-5">
        <div className="grid size-9 place-items-center rounded-lg bg-foreground text-background">
          <PanelsTopLeft className="size-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-heading text-sm font-semibold">WorkCrew</p>
          <p className="truncate text-xs text-muted-foreground">Local workflow desk</p>
        </div>
        <Badge variant="outline" className="gap-1.5 lg:hidden">
          <ShieldCheck /> Local
        </Badge>
      </div>

      {/* Primary CTA */}
      <div className="p-3 lg:p-4">
        <Button onClick={onNewRun} className="w-full">
          <Plus /> New run
        </Button>
      </div>

      {/* Run list */}
      <div className="min-h-0 flex-1 px-3 pb-3">
        <div className="flex items-center justify-between px-2 pb-2">
          <p className="text-[10px] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
            Runs
          </p>
          {runs.length > 0 && (
            <span className="font-mono text-[10px] text-muted-foreground">{runs.length}</span>
          )}
        </div>

        {historyStatus === "loading" && runs.length === 0 && (
          <p className="rounded-xl border border-dashed px-3 py-4 text-xs text-muted-foreground">
            Loading run history…
          </p>
        )}
        {historyStatus === "error" && historyError && (
          <p role="alert" className="mb-2 rounded-lg bg-destructive/8 px-3 py-2 text-xs text-destructive">
            {historyError}
          </p>
        )}
        {historyStatus === "ready" && runs.length === 0 && (
          <p className="rounded-xl border border-dashed px-3 py-4 text-xs leading-5 text-muted-foreground">
            No runs yet. Start one to create a local history.
          </p>
        )}

        {runs.length > 0 && (
          <ul
            aria-label="Runs"
            className="flex snap-x gap-2 overflow-x-auto pb-1 lg:max-h-[calc(100svh-250px)] lg:flex-col lg:overflow-y-auto lg:pr-1"
          >
            {runs.map((run) => {
              const selected = run.run_id === selectedRunId
              return (
                <li key={run.run_id} className="min-w-64 snap-start lg:min-w-0">
                  <button
                    type="button"
                    aria-label={`Open run ${run.run_id}`}
                    aria-current={selected ? "true" : undefined}
                    onClick={() => onSelect(run)}
                    className={cn(
                      "w-full rounded-xl border bg-background p-3 text-left transition-all hover:border-foreground/20 hover:bg-muted/35 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      selected && "border-foreground/25 bg-muted/45 shadow-sm"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs font-semibold">{run.run_id}</span>
                      <RunStatusBadge status={run.status} />
                    </div>
                    <p className="mt-2 truncate text-xs font-medium">
                      {run.source_name} → {run.workbook_name}
                    </p>
                    <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                      <time dateTime={run.started_at}>{formatStartTime(run.started_at)}</time>
                      <span className="flex shrink-0 items-center gap-1 font-mono">
                        <Clock3 className="size-3" aria-hidden="true" />
                        {formatDuration(run.duration)}
                      </span>
                    </div>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className="hidden border-t p-4 lg:block">
        <Badge variant="outline" className="gap-1.5 bg-background">
          <ShieldCheck /> Local only
        </Badge>
      </div>
    </aside>
  )
}

export { RunSidebar }
```

**Run card anatomy** (the densest repeated unit in the app): row 1 = monospace run id + status badge; row 2 = `source → workbook` in 12px medium; row 3 = relative start time + duration with a clock icon, both muted 11px. Selected state deepens the border and background rather than using an accent color.

---

## 3. New Run Form: `run-creation-form.tsx`

Six input slots in a two-column grid. **There is no in-app file browser** — each "Choose" button asks the local server to open the *host OS's own* file dialog (Finder on macOS via `osascript`, Tk elsewhere) and receives back an absolute path. This is the app's most distinctive interaction and any redesign must preserve it: the operator never types a path and never browses inside the web UI.

```tsx
// frontend/src/components/run-creation-form.tsx
import { useState, type FormEvent } from "react"
import { FileJson, FileSpreadsheet, FileText, Folder, Play } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { createRun, pickPath, type CreateRunInput, type PickMode, type RunRecord } from "@/lib/api"

type FieldKey = keyof CreateRunInput

const fields: Array<{
  key: FieldKey
  label: string
  description: string
  mode: PickMode
  required: boolean
  icon: typeof Folder
}> = [
  { key: "source",          label: "Source folder",   description: "Documents the workflow will read",   mode: "directory", required: true,  icon: Folder },
  { key: "workbook",        label: "Workbook",        description: "Excel template to fill",             mode: "file",      required: true,  icon: FileSpreadsheet },
  { key: "rules",           label: "Rules folder",    description: "Reference and extraction rules",     mode: "directory", required: true,  icon: Folder },
  { key: "workbook_schema", label: "Workbook schema", description: "JSON contract for writable cells",   mode: "file",      required: true,  icon: FileJson },
  { key: "scoping_answers", label: "Scoping answers", description: "Optional pre-answered questions",    mode: "file",      required: false, icon: FileText },
  { key: "review_policy",   label: "Review policy",   description: "Optional YAML policy override",      mode: "file",      required: false, icon: FileText },
]

const initialValues: CreateRunInput = {
  source: "", workbook: "", rules: "", workbook_schema: "",
  scoping_answers: null, review_policy: null,
}

function RunCreationForm({ onCreated }: { onCreated: (run: RunRecord) => void }) {
  const [values, setValues] = useState(initialValues)
  const [pickingKey, setPickingKey] = useState<FieldKey | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = fields.filter((field) => field.required).every((field) => Boolean(values[field.key]))

  async function choose(field: (typeof fields)[number]) {
    setPickingKey(field.key)
    setError(null)
    try {
      const picked = await pickPath(field.mode, `Choose ${field.label.toLowerCase()}`)
      if (picked) setValues((current) => ({ ...current, [field.key]: picked }))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to open the file chooser")
    } finally {
      setPickingKey(null)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready) return
    setSubmitting(true)
    setError(null)
    try {
      onCreated(await createRun(values))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start the run")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="mb-6">
        <p className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">
          New run
        </p>
        <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight">
          Assemble the working set.
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Choose local inputs with your system file chooser. WorkCrew copies them into an isolated run workspace before any agent begins.
        </p>
      </div>

      <form onSubmit={(event) => void handleSubmit(event)}>
        <Card className="bg-background shadow-lg shadow-black/4">
          <CardHeader className="border-b">
            <CardTitle>Run inputs</CardTitle>
            <CardDescription>Required inputs are marked. Original files stay untouched.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {fields.map((field) => {
              const Icon = field.icon
              const value = values[field.key]
              return (
                <div
                  key={field.key}
                  role="group"
                  aria-label={`${field.label} input`}
                  className="rounded-xl border bg-muted/18 p-3"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid size-9 shrink-0 place-items-center rounded-lg border bg-background">
                      <Icon className="size-4" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{field.label}</p>
                        {!field.required && (
                          <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                            Optional
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{field.description}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div
                      title={value ?? undefined}
                      className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                    >
                      {value || "Nothing selected"}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      type="button"
                      disabled={pickingKey !== null}
                      onClick={() => void choose(field)}
                    >
                      {pickingKey === field.key ? "Choosing…" : "Choose"}
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>
          <div className="flex flex-col gap-3 border-t bg-muted/20 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div aria-live="polite" className="text-sm">
              {error ? (
                <p className="text-destructive">{error}</p>
              ) : (
                <p className="text-muted-foreground">
                  {ready ? "Inputs ready. Start when you are." : "Select all four required inputs."}
                </p>
              )}
            </div>
            <Button type="submit" disabled={!ready || submitting} className="min-w-32">
              <Play /> {submitting ? "Starting…" : "Start run"}
            </Button>
          </div>
        </Card>
      </form>
    </div>
  )
}

export { RunCreationForm }
```

**Input slot anatomy**: a `rounded-xl border bg-muted/18 p-3` tile containing a 36px bordered icon square, label + optional "OPTIONAL" tag, a 12px description, and below them a row of [truncating monospace path readout] + [Choose button]. Empty state reads `Nothing selected`. The full path is exposed via the native `title` tooltip because it truncates.

---

## 4. Run Detail: `run-detail.tsx`

Header card + one of two middle blocks (scoping form when paused, progress otherwise) + artifacts. Opens a WebSocket for live events whenever the run is in a streamable state.

```tsx
// frontend/src/components/run-detail.tsx
import { useEffect } from "react"
import { Ban, Clock3, FolderOpen, PackageOpen, RotateCcw } from "lucide-react"

import { ArtifactViewer } from "@/components/artifact-viewer"
import { RunStatusBadge } from "@/components/run-status-badge"
import { ScopingQuestionForm } from "@/components/scoping-question-form"
import { WorkflowProgress } from "@/components/workflow-progress"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { RunRecord } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

function RunDetail({ run }: { run: RunRecord }) {
  // Store slices: streamRunId, streamEvents, connectRunStream, disconnectRunStream,
  //               scoping, resumeRun, cancelRun, retryRun, runAction
  const events = streamRunId === run.run_id ? streamEvents : []
  const streamable = run.status === "running" || run.status === "paused" || run.status === "failed"
  const streamLifecycle = run.status === "failed" ? "failed" : streamable ? "active" : "inactive"

  useEffect(() => {
    if (!streamable) return
    connectRunStream(run.run_id)
    return disconnectRunStream
  }, [connectRunStream, disconnectRunStream, run.run_id, streamLifecycle, streamable])

  const action = runAction.runId === run.run_id ? runAction : null
  const actionPending = action?.status === "submitting"

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
      {/* Header card: identity on the left, timing + actions on the right */}
      <Card className="bg-background shadow-lg shadow-black/4">
        <CardContent className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <RunStatusBadge status={run.status} />
              <span className="font-mono text-xs text-muted-foreground">{run.run_id}</span>
            </div>
            <h1 className="mt-3 truncate font-heading text-2xl font-semibold tracking-tight">
              {run.source_name} → {run.workbook_name}
            </h1>
          </div>
          <div className="flex flex-col gap-3 sm:items-end">
            <div className="grid gap-1 text-xs text-muted-foreground sm:text-right">
              <span className="flex items-center gap-1.5 sm:justify-end">
                <Clock3 className="size-3.5" />
                Started {new Date(run.start_time).toLocaleString()}
              </span>
              <span className="max-w-md truncate font-mono" title={run.workspace_path}>
                {run.workspace_path}
              </span>
            </div>
            {run.status === "running" && (
              <Button
                aria-label="Cancel run"
                variant="outline"
                size="sm"
                disabled={actionPending}
                className="text-destructive hover:bg-destructive/8"
                onClick={() => void cancelRun(run.run_id)}
              >
                <Ban /> {actionPending ? "Cancelling…" : "Cancel"}
              </Button>
            )}
            {(run.status === "failed" || run.status === "cancelled") && (
              <Button
                aria-label="Retry run"
                size="sm"
                disabled={actionPending}
                onClick={() => void retryRun(run.run_id)}
              >
                <RotateCcw /> {actionPending ? "Retrying…" : "Retry"}
              </Button>
            )}
            {action?.status === "error" && action.error && (
              <p role="alert" className="max-w-sm text-xs text-destructive">{action.error}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Paused runs swap the progress block for the question form */}
      {run.status === "paused" ? (
        <ScopingQuestionForm
          questions={scoping.runId === run.run_id ? scoping.questions : []}
          status={scoping.runId === run.run_id ? scoping.status : "loading"}
          error={scoping.runId === run.run_id ? scoping.error : null}
          onSubmit={(answers) => void resumeRun(run.run_id, answers)}
        />
      ) : (
        <WorkflowProgress run={run} events={events} />
      )}

      {run.status === "completed" ? (
        <ArtifactViewer runId={run.run_id} />
      ) : (
        <Card className="bg-muted/18">
          <CardHeader className="border-b">
            <CardTitle className="flex items-center gap-2">
              <PackageOpen className="size-4" /> Artifacts
            </CardTitle>
            <CardDescription>Outputs will appear here as the workflow advances.</CardDescription>
          </CardHeader>
          <CardContent className="flex items-center gap-3 text-sm text-muted-foreground">
            <FolderOpen className="size-4" />
            No artifacts available yet.
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export { RunDetail }
```

---

## 5. Stage Pipeline + Log Stream: `workflow-progress.tsx`

Two stacked pieces inside one card: a six-cell stage pipeline derived from the run's phase, and an auto-scrolling monospace event log.

```tsx
// frontend/src/components/workflow-progress.tsx
import { useEffect, useMemo, useRef } from "react"
import { Check, Circle, LoaderCircle, X } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { RunRecord, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

const stages = ["Scoping", "Filler", "Review", "Revision", "Re-review", "Finalize"]

// Backend phase name → stage index (0-5)
const phaseStage: Record<string, number> = {
  INITIALIZING: 0, INIT: 0, PREPARE_WORKSPACE: 0, BUILD_MANIFEST: 0,
  LOAD_SCHEMA: 0, CLAUDE_SCOPE: 0, AWAIT_SCOPING_ANSWERS: 0,
  CLAUDE_FILL: 1, VALIDATE: 1, WRITE_DRAFT: 1,
  CODEX_REVIEW: 2,
  CLAUDE_REVISE: 3, APPLY_ALLOWED_REVISIONS: 3,
  CODEX_REREVIEW: 4, HUMAN_REVIEW: 4,
  FINALIZE: 5,
}

type StageStatus = "pending" | "active" | "completed" | "failed"

// stageStatuses(run, events): everything before the current stage is "completed",
// the current stage is "active" (or "failed"/"completed" if the latest phase_change
// event says so), everything after is "pending". A completed run marks all six done.

const statusStyle: Record<StageStatus, string> = {
  pending:   "border-border bg-background text-muted-foreground",
  active:    "border-foreground/25 bg-foreground text-background shadow-sm",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed:    "border-red-200 bg-red-50 text-red-700",
}

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "completed") return <Check aria-hidden="true" />
  if (status === "failed") return <X aria-hidden="true" />
  if (status === "active") return <LoaderCircle className="animate-spin" aria-hidden="true" />
  return <Circle aria-hidden="true" />
}

function StagePipeline({ run, events }: { run: RunRecord; events: WorkflowEvent[] }) {
  const statuses = useMemo(() => stageStatuses(run, events), [events, run])
  return (
    <ol aria-label="Workflow stages" className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
      {stages.map((stage, index) => (
        <li
          key={stage}
          data-status={statuses[index]}
          aria-label={`${stage}: ${statuses[index]}`}
          className={cn(
            "flex items-center gap-2 rounded-xl border px-3 py-3 text-xs font-medium",
            statusStyle[statuses[index]]
          )}
        >
          <span className="[&_svg]:size-3.5"><StageIcon status={statuses[index]} /></span>
          <span>{stage}</span>
        </li>
      ))}
    </ol>
  )
}

function LogStream({ events }: { events: WorkflowEvent[] }) {
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }) }, [events])

  return (
    <div aria-label="Run log" aria-live="polite" className="max-h-64 overflow-y-auto rounded-xl border bg-muted/20">
      {events.length === 0 ? (
        <p className="px-4 py-6 text-sm text-muted-foreground">Waiting for workflow events…</p>
      ) : (
        <ul className="divide-y font-mono text-xs">
          {events.map((event, index) => {
            const details = workflowEventDetails(event)
            return (
              <li key={`${event.timestamp}-${index}`} className="flex gap-3 px-4 py-2.5">
                <time dateTime={event.timestamp} className="shrink-0 text-muted-foreground">
                  {new Date(event.timestamp).toLocaleTimeString([], {
                    hour: "2-digit", minute: "2-digit", second: "2-digit",
                  })}
                </time>
                <span className={cn(
                  "min-w-0 break-words",
                  (details.error !== null || details.phaseStatus === "failed") && "text-destructive"
                )}>
                  {details.logMessage}
                </span>
              </li>
            )
          })}
        </ul>
      )}
      <div ref={end} />
    </div>
  )
}

function WorkflowProgress({ run, events }: { run: RunRecord; events: WorkflowEvent[] }) {
  const failure = [...events].reverse().map(workflowEventDetails).find((event) => event.error !== null)
  return (
    <Card className="min-h-72 bg-background">
      <CardHeader className="border-b">
        <CardTitle>Workflow progress</CardTitle>
        <CardDescription>Live engine stages and timestamped progress messages.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StagePipeline run={run} events={events} />
        {failure?.error && (
          <p className="rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
            {failure.error}
          </p>
        )}
        <LogStream events={events} />
      </CardContent>
    </Card>
  )
}

export { LogStream, StagePipeline, WorkflowProgress }
```

**Pipeline responsive behavior**: `grid gap-2 sm:grid-cols-3 xl:grid-cols-6` — one column stacked on mobile, 2 rows of 3 on tablet, a single 6-across row on wide screens. Note the **active** stage inverts (dark fill, light text) while completed stages go emerald-tinted — the active step is the darkest thing on the page.

---

## 6. Scoping Questions: `scoping-question-form.tsx`

Rendered in place of the progress card when a run pauses. Four question types dispatch to four control components through a lookup map.

```tsx
// frontend/src/components/scoping-question-form.tsx
import { useState, type ComponentType, type FormEvent } from "react"
import { CircleHelp, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { ScopingAnswer, ScopingAnswers, ScopingQuestion, ScopingQuestionType } from "@/lib/api"

type FormStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type Choice = {
  key: string; value: string; label: string
  checked: boolean; onChange: (checked: boolean) => void
}

// Shared 2-column choice grid used by radio, checkbox, and confirm questions.
function ChoiceList({ questionId, inputType, choices }: {
  questionId: string
  inputType: "radio" | "checkbox"
  choices: Choice[]
}) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {choices.map((choice) => (
        <label
          key={choice.key}
          className="flex cursor-pointer items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-sm"
        >
          <input
            type={inputType}
            name={questionId}
            value={choice.value}
            checked={choice.checked}
            onChange={(event) => choice.onChange(event.target.checked)}
          />
          {choice.label}
        </label>
      ))}
    </div>
  )
}

function TextQuestion({ question, answer, onChange }: QuestionControlProps) {
  return (
    <textarea
      aria-label={question.question}
      value={typeof answer === "string" ? answer : ""}
      onChange={(event) => onChange(event.target.value)}
      rows={3}
      className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
    />
  )
}

// SingleSelectQuestion → ChoiceList inputType="radio",    choices from question.options
// MultiSelectQuestion  → ChoiceList inputType="checkbox", accumulates a string[] answer
// ConfirmQuestion      → ChoiceList inputType="radio",    hardcoded Yes/No → boolean

const questionControls: Record<ScopingQuestionType, ComponentType<QuestionControlProps>> = {
  text: TextQuestion,
  single_select: SingleSelectQuestion,
  multi_select: MultiSelectQuestion,
  confirm: ConfirmQuestion,
}

function ScopingQuestionForm({ questions, status, error, onSubmit }: ScopingQuestionFormProps) {
  const [answers, setAnswers] = useState<ScopingAnswers>({})
  const [validationError, setValidationError] = useState<string | null>(null)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // Every question must be answered before the run can resume.
    if (!questions.every((question) => answered(answers[question.id]))) {
      setValidationError("Answer every question before resuming the run.")
      return
    }
    onSubmit(answers)
  }

  return (
    <Card className="bg-background">
      <CardHeader className="border-b">
        <CardTitle role="heading" aria-level={2} className="flex items-center gap-2">
          <CircleHelp className="size-4" /> Scoping questions
        </CardTitle>
        <CardDescription>
          The workflow needs a few decisions before extraction can continue.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {status === "loading" || status === "idle" ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading questions…</p>
        ) : (
          <form className="space-y-4" onSubmit={submit}>
            {questions.map((question, index) => {
              const type = question.type ?? "text"
              const QuestionControl = questionControls[type]
              return (
                <fieldset key={question.id} className="rounded-xl border bg-muted/18 p-4">
                  <legend className="px-1 text-sm font-medium">
                    <span className="mr-2 font-mono text-xs text-muted-foreground">{index + 1}</span>
                    {question.question}
                  </legend>
                  <QuestionControl
                    question={question}
                    answer={answers[question.id]}
                    onChange={(value) => setAnswer(question.id, value)}
                  />
                </fieldset>
              )
            })}

            {(validationError || error) && (
              <p role="alert" className="text-sm text-destructive">{validationError ?? error}</p>
            )}
            <div className="flex justify-end">
              <Button type="submit" disabled={status === "submitting"}>
                <Send />
                {status === "submitting" ? "Resuming…" : "Submit answers"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

export { ScopingQuestionForm }
```

Note the native `<input type="radio">` / `<input type="checkbox">` — these are **unstyled browser defaults** wrapped in a bordered label tile. A redesign should give them a proper control treatment.

---

## 7. Artifact Viewer: `artifact-viewer.tsx`

Master-detail: a left list of artifacts (`17rem`) and a right preview pane that switches on artifact type — iframe for HTML (with a live height slider), rendered markdown, monospace JSON, and a download card for the final `.xlsx`.

```tsx
// frontend/src/components/artifact-viewer.tsx
import { useEffect, useState } from "react"
import Markdown from "react-markdown"
import { Check, Copy, Download, ExternalLink, File, LoaderCircle, PackageOpen } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { artifactUrl, listArtifacts, readArtifactText, type ArtifactSummary } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

// Fetches the artifact body as text, then renders markdown through react-markdown
// with a typographic class stack, or JSON in a monospace <pre>.
function TextArtifactPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // ...effect fetches readArtifactText(runId, artifact.name), guarded by `cancelled`

  if (error) {
    return (
      <p className="rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
        {error}
      </p>
    )
  }
  if (text === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="animate-spin" /> Loading preview…
      </p>
    )
  }
  if (artifact.type === "md") {
    return (
      <article className="max-w-none space-y-3 text-sm leading-7 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:pl-4 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_h1]:font-heading [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:font-heading [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_p]:text-foreground/85 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-4 [&_ul]:list-disc">
        <Markdown>{text}</Markdown>
      </article>
    )
  }
  return (
    <pre className="overflow-x-auto rounded-lg bg-muted p-4 font-mono text-xs leading-6">{text}</pre>
  )
}

function ArtifactPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [previewHeight, setPreviewHeight] = useState(480)
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle")
  const url = artifactUrl(runId, artifact.name)

  if (artifact.type === "html") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-3 text-xs text-muted-foreground">
            Preview height
            <input
              type="range" aria-label="Preview height"
              min="320" max="900" step="20"
              value={previewHeight}
              onChange={(event) => setPreviewHeight(Number(event.target.value))}
            />
            <span className="w-12 font-mono">{previewHeight}px</span>
          </label>
          <a href={url} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-4">
            <ExternalLink /> Open in new tab
          </a>
        </div>
        <iframe
          title={`${artifact.name} preview`}
          src={url}
          className="w-full rounded-lg border bg-white"
          style={{ height: `${previewHeight}px` }}
        />
      </div>
    )
  }

  if (artifact.type === "md" || artifact.type === "json") {
    return <TextArtifactPreview artifact={artifact} runId={runId} />
  }

  // xlsx — the terminal deliverable: download + copy-path card
  return (
    <div className="grid min-h-56 place-items-center rounded-xl border border-dashed bg-muted/18 p-6 text-center">
      <div>
        <Download className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 font-medium">Final workbook</p>
        <p className="mt-1 max-w-lg truncate font-mono text-xs text-muted-foreground" title={artifact.path}>
          {artifact.path}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <a href={url} download={artifact.name} aria-label={`Download ${artifact.name}`}
             className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/88">
            <Download /> Download {artifact.name}
          </a>
          <Button variant="outline" onClick={() => void copyPath()}>
            {copyStatus === "copied" ? <Check /> : <Copy />}
            Copy file path
          </Button>
        </div>
        {copyStatus === "copied" && <p className="mt-2 text-xs text-muted-foreground">Path copied</p>}
        {copyStatus === "failed" && <p className="mt-2 text-xs text-destructive">Unable to copy path</p>}
      </div>
    </div>
  )
}

function ArtifactViewer({ runId }: { runId: string }) {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[] | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // ...effect lists artifacts for the run and auto-selects the first one

  const selected = artifacts?.find((artifact) => artifact.name === selectedName)

  return (
    <Card className="overflow-hidden bg-background">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          <PackageOpen className="size-4" /> Artifacts
        </CardTitle>
        <CardDescription>Inspect generated reports and download the final workbook.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {/* loading / error / empty states omitted for brevity — all centered muted text */}
        {artifacts && artifacts.length > 0 && (
          <div className="grid min-h-80 lg:grid-cols-[17rem_minmax(0,1fr)]">
            <ul aria-label="Artifacts" className="border-b p-2 lg:border-r lg:border-b-0">
              {artifacts.map((artifact) => (
                <li key={artifact.name}>
                  <button
                    type="button"
                    onClick={() => setSelectedName(artifact.name)}
                    aria-label={`Preview ${artifact.name}`}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      artifact.name === selectedName ? "bg-foreground text-background" : "hover:bg-muted"
                    )}
                  >
                    <File className="size-4 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{artifact.name}</span>
                      <span className="mt-0.5 block font-mono text-[11px] opacity-65">
                        {formatBytes(artifact.size)}
                      </span>
                    </span>
                    <Badge variant="outline" className={cn(
                      "uppercase",
                      artifact.name === selectedName && "border-background/35 text-background"
                    )}>
                      {artifact.type}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
            <section className="min-w-0 p-4" aria-live="polite">
              {selected && <ArtifactPreview artifact={selected} runId={runId} />}
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export { ArtifactViewer }
```

---

## 8. Status Badge: `run-status-badge.tsx` + `lib/run-status.ts`

The single source of run-status color across sidebar cards and the detail header. **This is the app's entire accent palette** — everything else is grey.

```tsx
// frontend/src/components/run-status-badge.tsx
import { Badge } from "@/components/ui/badge"
import type { RunStatus } from "@/lib/api"
import { cn } from "@/lib/utils"
import { runStatusPresentation } from "@/lib/run-status"

function RunStatusBadge({ status }: { status: RunStatus }) {
  const presentation = runStatusPresentation[status]
  return (
    <Badge variant="outline" className={cn("gap-1.5", presentation.badgeClassName)}>
      <span className={cn("size-1.5 rounded-full", presentation.dotClassName)} />
      {presentation.label}
    </Badge>
  )
}

export { RunStatusBadge }
```

```ts
// frontend/src/lib/run-status.ts
const runStatusPresentation: Record<RunStatus, RunStatusPresentation> = {
  running: {
    label: "Running",
    badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dotClassName: "bg-emerald-500 animate-pulse",
    detailTitle: "Run in progress",
    detailDescription: "The engine is advancing through the workflow.",
    detailIcon: LoaderCircle,
    detailIconClassName: "animate-spin",
  },
  paused: {
    label: "Paused",
    badgeClassName: "border-amber-200 bg-amber-50 text-amber-700",
    dotClassName: "bg-amber-500",
    detailTitle: "Run paused",
    detailDescription: "The workflow is waiting for operator input.",
    detailIcon: CirclePause,
    detailIconClassName: "text-amber-600",
  },
  completed: {
    label: "Completed",
    badgeClassName: "border-sky-200 bg-sky-50 text-sky-700",
    dotClassName: "bg-sky-500",
    detailTitle: "Run completed",
    detailDescription: "The workflow finished successfully.",
    detailIcon: CheckCircle2,
    detailIconClassName: "text-sky-600",
  },
  failed: {
    label: "Failed",
    badgeClassName: "border-red-200 bg-red-50 text-red-700",
    dotClassName: "bg-red-500",
    detailTitle: "Run failed",
    detailDescription: "The workflow stopped before completion.",
    detailIcon: TriangleAlert,
    detailIconClassName: "text-red-600",
  },
  cancelled: {
    label: "Cancelled",
    badgeClassName: "border-stone-200 bg-stone-100 text-stone-600",
    dotClassName: "bg-stone-400",
    detailTitle: "Run cancelled",
    detailDescription: "The workflow was cancelled by the operator.",
    detailIcon: Ban,
    detailIconClassName: "text-stone-500",
  },
}
```

The `detail*` fields are defined but currently unused by any rendered component — available surface for a redesign that wants a richer status block.

---

## 9. UI Primitives (`components/ui/`)

Only three shadcn components are vendored. Everything else is composed from raw elements + utilities.

### `button.tsx`

```tsx
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/88",
        outline: "border bg-background hover:bg-muted",
        ghost: "hover:bg-muted",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        icon: "size-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
)

function Button({ className, variant, size, type = "button", ...props }:
  React.ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
```

Three variants, three sizes. Icons inside are auto-sized to 16px by the `[&_svg]:size-4` selector — call sites write `<Button><Plus /> New run</Button>` with no icon classes.

### `badge.tsx`

```tsx
const badgeVariants = cva(
  "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-4xl border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap transition-all focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground [a]:hover:bg-primary/80",
        secondary: "bg-secondary text-secondary-foreground [a]:hover:bg-secondary/80",
        destructive: "bg-destructive/10 text-destructive focus-visible:ring-destructive/20 dark:bg-destructive/20 dark:focus-visible:ring-destructive/40 [a]:hover:bg-destructive/20",
        outline: "border-border text-foreground [a]:hover:bg-muted [a]:hover:text-muted-foreground",
        ghost: "hover:bg-muted hover:text-muted-foreground dark:hover:bg-muted/50",
        link: "text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: { variant: "default" },
  }
)
// Renders a <span> (or a Radix Slot when asChild), fixed 20px height, fully rounded (rounded-4xl).
```

### `card.tsx`

```tsx
function Card({ className, size = "default", ...props }) {
  return (
    <div
      data-slot="card" data-size={size}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-xl bg-card py-(--card-spacing) text-sm text-card-foreground ring-1 ring-foreground/10 [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-xl *:[img:last-child]:rounded-b-xl",
        className
      )}
      {...props}
    />
  )
}

// CardHeader  — grid, auto-rows-min, px-(--card-spacing); adds bottom padding when it carries .border-b
// CardTitle   — font-heading text-base leading-snug font-medium
// CardDescription — text-sm text-muted-foreground
// CardAction  — col-start-2 row-span-2, self-start justify-self-end
// CardContent — px-(--card-spacing)
// CardFooter  — flex items-center rounded-b-xl border-t bg-muted/50 p-(--card-spacing)
```

**Key mechanic**: `Card` defines a local `--card-spacing` variable (16px, or 12px at `size="sm"`) that every subpart consumes for horizontal padding. Cards use `ring-1 ring-foreground/10` for their edge, not `border` — so a `border-b` on `CardHeader` reads as an internal divider. Section separation inside cards is done by adding `className="border-b"` to `CardHeader`.

---

## Data Model Summary

```ts
// frontend/src/lib/api.ts
export type PickMode = "directory" | "file"
export type RunStatus = "running" | "paused" | "completed" | "failed" | "cancelled"
export type ArtifactType = "html" | "md" | "xlsx" | "json"
export type ScopingQuestionType = "text" | "single_select" | "multi_select" | "confirm"
```

A **`RunSummary`** (sidebar list item) contains:

- `run_id: string` — timestamp-based id, e.g. `20260809-120000-abc123`
- `status: RunStatus`
- `started_at: string` — ISO 8601
- `duration: number` — seconds
- `source_name: string` — basename of the source folder, e.g. `source`
- `workbook_name: string` — basename of the workbook, e.g. `template.xlsx`

A **`RunRecord`** (detail view) contains:

- `run_id`, `status`, `source_name`, `workbook_name` — as above
- `start_time: string` — ISO 8601
- `workspace_path: string` — absolute path to the isolated run workspace
- `phase: string` — backend phase name, e.g. `CLAUDE_FILL`, `CODEX_REVIEW`, `FINALIZE`

A **`WorkflowEvent`** is a discriminated union on `type`, all sharing `timestamp: string`:

- `progress` — `phase: string`, `message: string`
- `phase_change` — `phase: string`, `status: "active" | "completed" | "failed"`
- `paused` — `reason: string`, `questions_artifact: string`
- `completed` — `final_xlsx: string`
- `failed` — `error: string`, `reason?: "cancelled"`

An **`ArtifactSummary`** contains:

- `name: string` — filename, e.g. `review_report.md`, `delivery.xlsx`
- `type: ArtifactType`
- `size: number` — bytes
- `path: string` — absolute path on disk

A **`ScopingQuestion`** contains:

- `id: string` — e.g. `Q1`
- `question: string` — the prompt text
- `type?: ScopingQuestionType` — defaults to `text`
- `options?: { value: string; label: string }[] | null` — for the select types

A **`CreateRunInput`** contains six absolute-path strings: `source`, `workbook`, `rules`, `workbook_schema` (all required) plus nullable `scoping_answers` and `review_policy`.

### API surface

| Call                       | Endpoint                                                                                   |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| `pickPath(mode, prompt)` | `POST /api/pick` → `{path: string \| null}` — **opens the host OS file dialog** |
| `createRun(input)`       | `POST /api/runs` → `RunRecord`                                                        |
| `listRuns()`             | `GET /api/runs` → `RunSummary[]`                                                      |
| `getRun(id)`             | `GET /api/runs/{id}` → `RunRecord`                                                    |
| `resumeRun(id, answers)` | `POST /api/runs/{id}/resume` → `RunRecord`                                            |
| `cancelRun(id)`          | `POST /api/runs/{id}/cancel` → `RunRecord`                                            |
| `listArtifacts(id)`      | `GET /api/runs/{id}/artifacts` → `ArtifactSummary[]`                                  |
| `artifactUrl(id, name)`  | `GET /api/runs/{id}/artifacts/{name}` — raw bytes                                       |
| live events                | `WebSocket /ws/runs/{id}` → `WorkflowEvent` frames                                    |

Errors: the server returns `{detail: string}`; `readResponse` throws `new Error(detail)`, and every component surfaces `cause.message` directly in the UI.

### State management (`store/use-app-store.ts`, Zustand)

```ts
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
  scoping: { runId: string | null; questions: ScopingQuestion[]; status: ScopingStatus; error: string | null }
  runAction: { runId: string | null; kind: "cancel" | "retry" | null; status: "idle" | "submitting" | "error"; error: string | null }
  // actions: openNewRun, showRun, startHistoryLoad, receiveRuns, failHistoryLoad,
  //          connectRunStream, disconnectRunStream, loadScopingQuestions,
  //          resumeRun, cancelRun, retryRun
}
```

A single module-level `activeSocket: WebSocket | null` guarantees one live stream at a time; every socket callback re-checks `activeSocket === socket` before writing state. Incoming events fold into `currentRun` (`phase` and `status` advance) and the sidebar summary list stays sorted newest-first. A `paused` event auto-triggers `loadScopingQuestions`.

---

## Design Tokens (CSS Variables)

Defined in `src/index.css`. Tailwind v4 with **no config file** — the `@theme inline` block maps each `--color-*` utility namespace onto a raw `--*` variable, so `bg-muted`, `text-muted-foreground`, `border-border` etc. all resolve here. Both light (`:root`) and dark (`.dark`) scales exist; **the app never toggles `.dark` today**, so only the light scale ships — a redesign could wire the toggle.

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/geist";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Geist Variable', sans-serif;
    /* every semantic color is aliased into the Tailwind color namespace */
    --color-background: var(--background);      --color-foreground: var(--foreground);
    --color-card: var(--card);                  --color-card-foreground: var(--card-foreground);
    --color-popover: var(--popover);            --color-popover-foreground: var(--popover-foreground);
    --color-primary: var(--primary);            --color-primary-foreground: var(--primary-foreground);
    --color-secondary: var(--secondary);        --color-secondary-foreground: var(--secondary-foreground);
    --color-muted: var(--muted);                --color-muted-foreground: var(--muted-foreground);
    --color-accent: var(--accent);              --color-accent-foreground: var(--accent-foreground);
    --color-destructive: var(--destructive);
    --color-border: var(--border);              --color-input: var(--input);      --color-ring: var(--ring);
    --color-chart-1..5: var(--chart-1..5);
    --color-sidebar*: var(--sidebar*);          /* full sidebar sub-scale, currently unused by components */
    /* radius scale derived from a single --radius */
    --radius-sm:  calc(var(--radius) * 0.6);
    --radius-md:  calc(var(--radius) * 0.8);
    --radius-lg:  var(--radius);
    --radius-xl:  calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: oklch(1 0 0);                 /* pure white page */
    --foreground: oklch(0.145 0 0);             /* near-black text */
    --card: oklch(1 0 0);                       --card-foreground: oklch(0.145 0 0);
    --popover: oklch(1 0 0);                    --popover-foreground: oklch(0.145 0 0);
    --primary: oklch(0.205 0 0);                /* dark grey — the CTA fill */
    --primary-foreground: oklch(0.985 0 0);
    --secondary: oklch(0.97 0 0);               --secondary-foreground: oklch(0.205 0 0);
    --muted: oklch(0.97 0 0);                   --muted-foreground: oklch(0.556 0 0);
    --accent: oklch(0.97 0 0);                  --accent-foreground: oklch(0.205 0 0);
    --destructive: oklch(0.577 0.245 27.325);   /* the one saturated token */
    --border: oklch(0.922 0 0);
    --input: oklch(0.922 0 0);
    --ring: oklch(0.708 0 0);
    --chart-1: oklch(0.87 0 0);   --chart-2: oklch(0.556 0 0);  --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);  --chart-5: oklch(0.269 0 0);  /* grey ramp, no chart in the app yet */
    --radius: 0.625rem;                          /* 10px — everything derives from this */
    --sidebar: oklch(0.985 0 0);                 --sidebar-foreground: oklch(0.145 0 0);
    --sidebar-primary: oklch(0.205 0 0);         --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.97 0 0);           --sidebar-accent-foreground: oklch(0.205 0 0);
    --sidebar-border: oklch(0.922 0 0);          --sidebar-ring: oklch(0.708 0 0);
}

.dark {
    --background: oklch(0.145 0 0);              --foreground: oklch(0.985 0 0);
    --card: oklch(0.205 0 0);                    --card-foreground: oklch(0.985 0 0);
    --popover: oklch(0.205 0 0);                 --popover-foreground: oklch(0.985 0 0);
    --primary: oklch(0.922 0 0);                 --primary-foreground: oklch(0.205 0 0);
    --secondary: oklch(0.269 0 0);               --secondary-foreground: oklch(0.985 0 0);
    --muted: oklch(0.269 0 0);                   --muted-foreground: oklch(0.708 0 0);
    --accent: oklch(0.269 0 0);                  --accent-foreground: oklch(0.985 0 0);
    --destructive: oklch(0.704 0.191 22.216);
    --border: oklch(1 0 0 / 10%);                --input: oklch(1 0 0 / 15%);   --ring: oklch(0.556 0 0);
    --sidebar: oklch(0.205 0 0);                 --sidebar-foreground: oklch(0.985 0 0);
    --sidebar-primary: oklch(0.488 0.243 264.376);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.269 0 0);          --sidebar-accent-foreground: oklch(0.985 0 0);
    --sidebar-border: oklch(1 0 0 / 10%);        --sidebar-ring: oklch(0.556 0 0);
}

@layer base {
  * { @apply border-border outline-ring/50; }
  body { @apply min-w-80 bg-background text-foreground antialiased; }
  html { @apply font-sans; }
}
```

**Hardcoded Tailwind palette colors outside the token system** (the status accents — a redesign should decide whether to tokenize them):
`emerald-50/200/500/700`, `amber-50/200/500/600/700`, `sky-50/200/500/600/700`, `red-50/200/500/600/700`, `stone-100/200/400/500/600`.

**Typography scale in use**: `text-[10px]` (uppercase eyebrows) · `text-[11px]` (metadata) · `text-xs` (12px — most secondary text, all monospace) · `text-sm` (14px — body) · `text-base` (card titles) · `text-2xl` (run detail h1) · `text-3xl` (page h1). Tracking: `tracking-[0.16em]` and `tracking-[0.18em]` on uppercase eyebrows, `tracking-tight` on large headings.

**Spacing rhythm**: cards gap `4` (16px), grids gap `2`–`3`, page padding `p-5 / sm:p-8 / lg:p-10`.

---

## Interaction Patterns

Preserve these — they carry the product's meaning:

- **Native OS file chooser.** Clicking any "Choose" button calls `POST /api/pick`; the local server opens the *operating system's own* dialog (Finder / Tk) and returns an absolute path. During the call the button reads "Choosing…" and **all six Choose buttons disable** (`pickingKey !== null`). Cancelling the OS dialog resolves to `null` and leaves the previous value untouched. There is no in-app file browser to redesign — the path readout and the button are the entire UI surface.
- **Three-view swap, no router.** `view` in the store flips between the empty state, the creation form, and run detail. Selecting a run in the sidebar fetches the full record before switching.
- **Live WebSocket stream.** Opened for `running` / `paused` / `failed` runs; each event advances the stage pipeline and appends to the log, which auto-scrolls to the bottom via a sentinel `<div ref={end}>` + `scrollIntoView`.
- **Stage pipeline as the progress metaphor.** Six fixed stages; the active one inverts to a dark fill with a spinning loader, completed ones go emerald, failed ones red, pending ones stay outlined grey.
- **Pause → question form.** A `paused` run replaces the progress card with the scoping form; all questions must be answered before "Submit answers" resumes the run. Validation error appears inline above the button.
- **Status-driven actions.** `running` shows Cancel (destructive-tinted outline button); `failed`/`cancelled` show Retry. Both go through a shared `runAction` state that renders "Cancelling…"/"Retrying…" and an inline error.
- **Artifact master-detail.** Selecting an artifact inverts its list row (dark fill, light text, badge border flips). The HTML preview has a **live range slider (320–900px) resizing the iframe**, plus "Open in new tab". The xlsx artifact is a download card with a copy-path button whose icon swaps to a checkmark on success.
- **Truncation + `title` tooltips everywhere.** Absolute paths, run ids, and `source → workbook` labels all `truncate` in monospace with the full value in a native `title` attribute. Any redesign has to keep long POSIX paths from breaking layout.
- **Responsive collapse.** Below `lg`, the sidebar becomes a top bar and the run list scrolls horizontally with scroll-snap; the stage pipeline goes 6 → 3 → 1 columns; the artifact master-detail stacks.
- **Focus rings are explicit.** Custom controls use `focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none`; buttons use `focus-visible:ring-3`.
- **No hover animations beyond color.** `transition-colors` / `transition-all` on backgrounds and borders; the only motion in the app is `animate-spin` on loaders and `animate-pulse` on the running-status dot.
