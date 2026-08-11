# WorkCrew — Full Frontend Component Reference for Redesign

WorkCrew is a **local-first document-to-workbook workflow desk**. An operator picks a folder of source documents and an Excel workbook template, writes a sentence describing the task, and optionally supplies extraction rules; the backend then runs a multi-stage agent pipeline (Scoping → Filler → Review → Revision → Re-review → Finalize) that fills the workbook and produces auditable artifacts. The workbook's field schema is derived by the scoping pass, not uploaded. The UI is served by a local Python server on loopback and opened in the operator's own browser — there is no cloud, no login, no multi-user state.

**Tech stack**: React 19, TypeScript, Vite 8, Tailwind CSS v4 (`@theme inline`, no config file), shadcn/ui (only Badge/Button/Card vendored), Radix UI primitives, lucide-react icons, Zustand 5, react-markdown, Geist Variable font.

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

Inside `view === "run"`, the right pane stacks three cards vertically with `gap-4`:

```
┌──────────────────────────────────────────────┐
│ header card — status badge, run id, title,   │
│               started at, workspace path,    │
│               Cancel / Retry action          │
├──────────────────────────────────────────────┤
│ status === "paused" → ScopingQuestionForm    │
│ otherwise           → WorkflowProgress       │
├──────────────────────────────────────────────┤
│ status === "completed" → ArtifactViewer      │
│ otherwise              → empty artifacts card│
└──────────────────────────────────────────────┘
```

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

      {/* Run history */}
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

      {/* Trust footer — desktop only */}
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

**Run card anatomy** (the densest repeated element in the app):

```
┌────────────────────────────────────────┐
│ 20260810-215131-7d550b   [● Running]   │  ← font-mono id + status badge
│ charity-reports → charities.xlsx       │  ← truncated source → workbook
│ Aug 10, 9:51 PM             ⏱ 3m 5s    │  ← time + monospace duration
└────────────────────────────────────────┘
   rounded-xl border · hover:bg-muted/35 · selected: bg-muted/45 + shadow-sm
```

---

## 3. New Run Form: `run-creation-form.tsx`

Four inputs in one card: two native path pickers (required), a free-text task description (required), and a rules block with a three-way source toggle (optional). Nothing is uploaded — the operator picks host paths through the backend's native chooser (`POST /api/pick`), so the form only ever holds absolute path strings.

```tsx
// frontend/src/components/run-creation-form.tsx
import { useState, type FormEvent } from "react"
import { FileSpreadsheet, Folder, Play } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { createRun, pickPath, type CreateRunInput, type PickMode, type RulesMode, type RunRecord } from "@/lib/api"
import { cn } from "@/lib/utils"

type PathKey = "source" | "workbook"

const paths: Array<{ key: PathKey; label: string; description: string; mode: PickMode; icon: typeof Folder }> = [
  { key: "source",   label: "Source folder", description: "Documents the workflow will read", mode: "directory", icon: Folder },
  { key: "workbook", label: "Workbook",      description: "Excel template to fill",           mode: "file",      icon: FileSpreadsheet },
]

const rulesModes: Array<{ mode: RulesMode; label: string }> = [
  { mode: "none", label: "No rules" },
  { mode: "text", label: "Describe them" },
  { mode: "file", label: "Use a text file" },
]

function RunCreationForm({ onCreated }: { onCreated: (run: RunRecord) => void }) {
  const [values, setValues] = useState<Record<PathKey, string>>({ source: "", workbook: "" })
  const [task, setTask] = useState("")
  const [rulesMode, setRulesMode] = useState<RulesMode>("none")
  const [rulesText, setRulesText] = useState("")
  const [rulesFile, setRulesFile] = useState("")
  const [pickingKey, setPickingKey] = useState<PathKey | "rules" | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The submit button unlocks only when both paths are picked, the task is
  // non-empty, and the chosen rules mode has its own input satisfied.
  const ready =
    Boolean(values.source) &&
    Boolean(values.workbook) &&
    task.trim().length > 0 &&
    (rulesMode !== "text" || rulesText.trim().length > 0) &&
    (rulesMode !== "file" || Boolean(rulesFile))

  async function choose(key: PathKey | "rules", mode: PickMode, prompt: string) {
    // Opens the host's native chooser via POST /api/pick; a cancel resolves
    // to null and leaves the current value alone.
    setPickingKey(key)
    setError(null)
    try {
      const picked = await pickPath(mode, prompt)
      if (picked === null) return
      if (key === "rules") setRulesFile(picked)
      else setValues((current) => ({ ...current, [key]: picked }))
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
    const input: CreateRunInput = {
      source: values.source,
      workbook: values.workbook,
      task: task.trim(),
      rules_text: rulesMode === "text" ? rulesText.trim() : null,
      rules_file: rulesMode === "file" ? rulesFile : null,
      scoping_answers: null,
      review_policy: null,
    }
    try {
      onCreated(await createRun(input))   // POST /api/runs → switches the view to the new run
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start the run")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      {/* Page heading */}
      <div className="mb-6">
        <p className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">New run</p>
        <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight">Assemble the working set.</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Point WorkCrew at your documents and workbook, then say what you want done.
          The scoping pass reads the workbook and derives the field schema itself.
        </p>
      </div>

      <form onSubmit={(event) => void handleSubmit(event)}>
        <Card className="bg-background shadow-lg shadow-black/4">
          <CardHeader className="border-b">
            <CardTitle>Run inputs</CardTitle>
            <CardDescription>
              Your files are never modified. Results are written to a
              workcrew-output folder inside the source folder.
            </CardDescription>
          </CardHeader>

          {/* Two path pickers, side by side on sm+ */}
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {paths.map((field) => {
              const Icon = field.icon
              const value = values[field.key]
              return (
                <div key={field.key} role="group" aria-label={`${field.label} input`}
                     className="rounded-xl border bg-muted/18 p-3">
                  <div className="flex items-start gap-3">
                    <div className="grid size-9 shrink-0 place-items-center rounded-lg border bg-background">
                      <Icon className="size-4" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{field.label}</p>
                        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                          Required
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{field.description}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div title={value || undefined}
                         className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground">
                      {value || "Nothing selected"}
                    </div>
                    <Button size="sm" variant="outline" type="button" disabled={pickingKey !== null}
                            onClick={() => void choose(field.key, field.mode, `Choose ${field.label.toLowerCase()}`)}>
                      {pickingKey === field.key ? "Choosing…" : "Choose"}
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>

          {/* Task — the sentence the whole run is derived from */}
          <CardContent>
            <div role="group" aria-label="Task input" className="rounded-xl border bg-muted/18 p-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Task</p>
                <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">Required</span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                What should this run produce? The workbook schema is derived from this.
              </p>
              <textarea
                aria-label="Task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                rows={4}
                placeholder="e.g. Fill one row per charity folder from the annual reports, keyed by registration number."
                className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
            </div>
          </CardContent>

          {/* Rules — segmented toggle reveals a textarea or a file picker */}
          <CardContent>
            <div role="group" aria-label="Rules input" className="rounded-xl border bg-muted/18 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">Rules</p>
                    <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">Optional</span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Extraction conventions the agents should follow
                  </p>
                </div>
                <div role="radiogroup" aria-label="Rules source" className="flex gap-1">
                  {rulesModes.map((option) => (
                    <button
                      key={option.mode}
                      type="button"
                      role="radio"
                      aria-checked={rulesMode === option.mode}
                      onClick={() => setRulesMode(option.mode)}
                      className={cn(
                        "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                        rulesMode === option.mode
                          ? "border-foreground/25 bg-foreground text-background"
                          : "bg-background hover:bg-muted"
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {rulesMode === "text" && (
                <textarea
                  aria-label="Rules"
                  value={rulesText}
                  onChange={(event) => setRulesText(event.target.value)}
                  rows={4}
                  placeholder="e.g. Charity IDs are CHA- followed by the registration number. Income under 100k is Small, under 1m Medium, otherwise Large."
                  className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                />
              )}

              {rulesMode === "file" && (
                <div className="mt-3 flex items-center gap-2">
                  <div title={rulesFile || undefined}
                       className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground">
                    {rulesFile || "Nothing selected"}
                  </div>
                  <Button size="sm" variant="outline" type="button" disabled={pickingKey !== null}
                          onClick={() => void choose("rules", "file", "Choose rules file")}>
                    {pickingKey === "rules" ? "Choosing…" : "Choose"}
                  </Button>
                </div>
              )}
            </div>
          </CardContent>

          {/* Sticky-feeling footer bar: live readiness copy on the left, submit on the right */}
          <div className="flex flex-col gap-3 border-t bg-muted/20 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div aria-live="polite" className="text-sm">
              {error ? (
                <p className="text-destructive">{error}</p>
              ) : (
                <p className="text-muted-foreground">
                  {ready
                    ? "Inputs ready. Start when you are."
                    : "Select the source folder and workbook, then describe the task."}
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

**Input group anatomy** — every one of the three groups shares the same shell: `rounded-xl border bg-muted/18 p-3`, a `text-sm font-medium` label paired with a tiny uppercase `Required`/`Optional` tag, a `text-xs text-muted-foreground` description, then the control. Path controls pair a truncating monospace "value well" with a `size="sm" variant="outline"` **Choose** button that reads `Choosing…` while the native dialog is open (all pickers disable while any one is open).

---

## 4. Run Detail: `run-detail.tsx`

The run header card plus the two swappable body sections. Opens a WebSocket while the run is streamable and tears it down on unmount.

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
  // scoping, resumeRun, cancelRun, retryRun, runAction
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
      {/* Header card */}
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
              <Button aria-label="Cancel run" variant="outline" size="sm" disabled={actionPending}
                      className="text-destructive hover:bg-destructive/8"
                      onClick={() => void cancelRun(run.run_id)}>
                <Ban /> {actionPending ? "Cancelling…" : "Cancel"}
              </Button>
            )}
            {(run.status === "failed" || run.status === "cancelled") && (
              <Button aria-label="Retry run" size="sm" disabled={actionPending}
                      onClick={() => void retryRun(run.run_id)}>
                <RotateCcw /> {actionPending ? "Retrying…" : "Retry"}
              </Button>
            )}
            {action?.status === "error" && action.error && (
              <p role="alert" className="max-w-sm text-xs text-destructive">{action.error}</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Body: questions when paused, live progress otherwise */}
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

      {/* Artifacts: real viewer only once completed */}
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

Action affordances are status-exclusive: **Cancel** (outline button tinted `text-destructive`) only while `running`; **Retry** (solid button) only when `failed` or `cancelled`; neither while `paused` or `completed`.

---

## 5. Stage Pipeline + Log Stream: `workflow-progress.tsx`

Two stacked sub-components inside one card: a six-cell stage strip and an auto-scrolling timestamped log. Both are driven by the same `WorkflowEvent[]`, so they never disagree.

```tsx
// frontend/src/components/workflow-progress.tsx
import { useEffect, useMemo, useRef } from "react"
import { Check, Circle, LoaderCircle, X } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { RunRecord, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

const stages = ["Scoping", "Filler", "Review", "Revision", "Re-review", "Finalize"]

// Backend phase name → stage index. Several phases collapse into one cell.
const phaseStage: Record<string, number> = {
  INITIALIZING: 0, INIT: 0, PREPARE_WORKSPACE: 0, BUILD_MANIFEST: 0,
  OUTLINE_WORKBOOK: 0, LOAD_SCHEMA: 0, CLAUDE_SCOPE: 0, AWAIT_SCOPING_ANSWERS: 0,
  CLAUDE_FILL: 1, VALIDATE: 1, WRITE_DRAFT: 1,
  CODEX_REVIEW: 2,
  CLAUDE_REVISE: 3, APPLY_ALLOWED_REVISIONS: 3,
  CODEX_REREVIEW: 4, HUMAN_REVIEW: 4,
  FINALIZE: 5,
}

type StageStatus = "pending" | "active" | "completed" | "failed"

// Everything before the current stage is completed, everything after is pending;
// the current cell is active, completed, or failed depending on the latest event.
function stageStatuses(run: RunRecord, events: WorkflowEvent[]): StageStatus[] {
  if (run.status === "completed" ||
      events.some((event) => workflowEventDetails(event).runStatus === "completed")) {
    return stages.map(() => "completed")
  }

  const phaseEvent = [...events].reverse().map(workflowEventDetails)
    .find((event) => event.phaseStatus !== null)
  const phase = phaseEvent?.phase ?? run.phase
  const current = phaseStage[phase] ?? 0
  const failed =
    run.status === "failed" ||
    events.some((event) => workflowEventDetails(event).runStatus === "failed") ||
    phaseEvent?.phaseStatus === "failed"
  const currentStatus: StageStatus = failed
    ? "failed"
    : phaseEvent?.phaseStatus === "completed" ? "completed" : "active"

  return stages.map((_, index) => {
    if (index < current) return "completed"
    if (index === current) return currentStatus
    return "pending"
  })
}

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

  // Every new event pins the view to the bottom of the log.
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }) }, [events])

  return (
    <div aria-label="Run log" aria-live="polite"
         className="max-h-64 overflow-y-auto rounded-xl border bg-muted/20">
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

Stage strip responsive shape: **1 column** on mobile → `sm:grid-cols-3` (two rows of three) → `xl:grid-cols-6` (one row). The active cell is the only inverted surface in the app (`bg-foreground text-background`), which makes "where are we" readable at a glance.

### Event → UI mapping (`lib/workflow-events.ts`)

One pure function turns each socket event into the four things the UI needs, so no component branches on `event.type` itself.

```ts
// frontend/src/lib/workflow-events.ts
type WorkflowEventDetails = {
  phase: string | null
  phaseStatus: "active" | "completed" | "failed" | null
  runStatus: RunStatus | null
  logMessage: string
  error: string | null
}

function workflowEventDetails(event: WorkflowEvent): WorkflowEventDetails {
  if (event.type === "progress")
    return { phase: event.phase, phaseStatus: null, runStatus: null, logMessage: event.message, error: null }
  if (event.type === "phase_change")
    return { phase: event.phase, phaseStatus: event.status, runStatus: null,
             logMessage: `${event.phase} ${event.status === "active" ? "started" : event.status}`, error: null }
  if (event.type === "paused")
    return { phase: null, phaseStatus: null, runStatus: "paused", logMessage: event.reason, error: null }
  if (event.type === "completed")
    return { phase: "FINALIZE", phaseStatus: null, runStatus: "completed",
             logMessage: `Run completed: ${event.final_xlsx}`, error: null }
  if (event.reason === "cancelled")
    // A cancel is a stop, not a fault: no red styling, no failure banner.
    return { phase: null, phaseStatus: null, runStatus: "cancelled", logMessage: event.error, error: null }
  return { phase: null, phaseStatus: null, runStatus: "failed", logMessage: event.error, error: event.error }
}
```

---

## 6. Scoping Questions: `scoping-question-form.tsx`

Replaces the progress card while the run is `paused`. The backend asks in rounds; each round is a fresh set of questions of four possible types, and every non-text question gets an optional free-text note beside it.

```tsx
// frontend/src/components/scoping-question-form.tsx
import { useEffect, useState, type ComponentType, type FormEvent } from "react"
import { CircleHelp, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { ScopingAnswers, ScopingAnswerValue, ScopingQuestion, ScopingQuestionType } from "@/lib/api"

type FormStatus = "idle" | "loading" | "ready" | "submitting" | "error"

// Shared option renderer for radio/checkbox questions: two columns on sm+.
function ChoiceList({ questionId, inputType, choices }: {
  questionId: string
  inputType: "radio" | "checkbox"
  choices: Array<{ key: string; value: string; label: string; checked: boolean; onChange: (checked: boolean) => void }>
}) {
  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {choices.map((choice) => (
        <label key={choice.key}
               className="flex cursor-pointer items-center gap-3 rounded-lg border bg-background px-3 py-2.5 text-sm">
          <input type={inputType} name={questionId} value={choice.value} checked={choice.checked}
                 onChange={(event) => choice.onChange(event.target.checked)} />
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

// SingleSelectQuestion → ChoiceList with radios over question.options
// MultiSelectQuestion  → ChoiceList with checkboxes; toggles into/out of an array
// ConfirmQuestion      → ChoiceList with radios over a fixed Yes / No pair (boolean answer)

const questionControls: Record<ScopingQuestionType, ComponentType<QuestionControlProps>> = {
  text: TextQuestion,
  single_select: SingleSelectQuestion,
  multi_select: MultiSelectQuestion,
  confirm: ConfirmQuestion,
}

function ScopingQuestionForm({ questions, status, error, onSubmit }: ScopingQuestionFormProps) {
  const [values, setValues] = useState<Record<string, ScopingAnswerValue>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [validationError, setValidationError] = useState<string | null>(null)

  // A later round reuses this component, so its answers must not carry
  // over from the round before.
  useEffect(() => {
    setValues({})
    setNotes({})
    setValidationError(null)
  }, [questions])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!questions.every((question) => answered(values[question.id]))) {
      setValidationError("Answer every question before resuming the run.")
      return
    }
    const answers: ScopingAnswers = Object.fromEntries(
      questions.map((question) => [
        question.id,
        { value: values[question.id], note: notes[question.id]?.trim() || null },
      ])
    )
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
                    answer={values[question.id]}
                    onChange={(value) => setValue(question.id, value)}
                  />

                  {/* Options can never cover everything — every non-text question
                      carries a free-text note beside it. */}
                  {type !== "text" && (
                    <label className="mt-3 block">
                      <span className="text-xs text-muted-foreground">
                        Add anything the options do not cover (optional)
                      </span>
                      <textarea
                        aria-label={`Note for ${question.question}`}
                        value={notes[question.id] ?? ""}
                        onChange={(event) =>
                          setNotes((current) => ({ ...current, [question.id]: event.target.value }))}
                        rows={2}
                        className="mt-1.5 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                      />
                    </label>
                  )}
                </fieldset>
              )
            })}

            {(validationError || error) && (
              <p role="alert" className="text-sm text-destructive">{validationError ?? error}</p>
            )}
            <div className="flex justify-end">
              <Button type="submit" disabled={status === "submitting"}>
                <Send /> {status === "submitting" ? "Resuming…" : "Submit answers"}
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

Each question is a `<fieldset>` on the same `rounded-xl border bg-muted/18` surface as the creation-form groups, numbered by a monospace index inside the `<legend>`. Validation is all-or-nothing: one inline `role="alert"` line, no per-field error states.

---

## 7. Artifact Viewer: `artifact-viewer.tsx`

Shown only once the run completes. A master–detail split: a file list on the left, a type-aware preview on the right. Three preview modes — HTML in a resizable iframe, Markdown/JSON as text, and the final `.xlsx` as a download panel.

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

// Fetches the artifact body as text, then renders Markdown through react-markdown
// with a typographic utility set, or JSON in a monospace <pre>.
function TextArtifactPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => { /* readArtifactText(runId, artifact.name), cancelled-flag guarded */ },
    [artifact.name, runId])

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
  return <pre className="overflow-x-auto rounded-lg bg-muted p-4 font-mono text-xs leading-6">{text}</pre>
}

function ArtifactPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [previewHeight, setPreviewHeight] = useState(480)
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle")
  const url = artifactUrl(runId, artifact.name)

  useEffect(() => setCopyStatus("idle"), [artifact.name])

  // HTML → live iframe with a height slider and an "open in new tab" escape hatch
  if (artifact.type === "html") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-3 text-xs text-muted-foreground">
            Preview height
            <input type="range" aria-label="Preview height" min="320" max="900" step="20"
                   value={previewHeight}
                   onChange={(event) => setPreviewHeight(Number(event.target.value))} />
            <span className="w-12 font-mono">{previewHeight}px</span>
          </label>
          <a href={url} target="_blank" rel="noreferrer"
             className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-4">
            <ExternalLink /> Open in new tab
          </a>
        </div>
        <iframe title={`${artifact.name} preview`} src={url}
                className="w-full rounded-lg border bg-white"
                style={{ height: `${previewHeight}px` }} />
      </div>
    )
  }

  if (artifact.type === "md" || artifact.type === "json") {
    return <TextArtifactPreview artifact={artifact} runId={runId} />
  }

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(artifact.path)
      setCopyStatus("copied")
    } catch {
      setCopyStatus("failed")
    }
  }

  // xlsx → dashed download panel with the host path and a copy-path action
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

  // Lists artifacts for the run and keeps the selection valid, defaulting to
  // the first item; cancelled-flag guarded.
  useEffect(() => { /* listArtifacts(runId) → setArtifacts / setSelectedName / setError */ }, [runId])

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
        {artifacts === null && error === null && (
          <p className="flex min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="animate-spin" /> Loading artifacts…
          </p>
        )}
        {error && (
          <p className="m-4 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </p>
        )}
        {artifacts?.length === 0 && (
          <p className="grid min-h-40 place-items-center text-sm text-muted-foreground">
            No artifacts available.
          </p>
        )}
        {artifacts && artifacts.length > 0 && (
          <div className="grid min-h-80 lg:grid-cols-[17rem_minmax(0,1fr)]">
            {/* Master list */}
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
                    <Badge variant="outline"
                           className={cn("uppercase",
                             artifact.name === selectedName && "border-background/35 text-background")}>
                      {artifact.type}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
            {/* Detail pane */}
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

The selected list row is inverted (`bg-foreground text-background`), and its type badge flips to `border-background/35 text-background` so it stays legible on the dark row. Below `lg` the split stacks: the list becomes a full-width block with a bottom border, the preview follows underneath.

---

## 8. Status Badge: `run-status-badge.tsx` + `lib/run-status.ts`

One presentation map is the single source of truth for every status color in the app — badge classes, the pulse dot, and the longer detail-view copy and icon.

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

`running` is the only status with motion: a pulsing dot in the badge and a spinning icon in detail contexts.

---

## 9. UI Primitives (`components/ui/`)

Only three shadcn components are vendored. Everything else in the app is raw elements plus utilities.

### Button

```tsx
// frontend/src/components/ui/button.tsx
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

Icons are passed as children (`<Button><Plus /> New run</Button>`) and auto-sized to `size-4` by the base class. `type` defaults to `"button"`, so only explicit `type="submit"` buttons submit a form.

### Badge

```tsx
// frontend/src/components/ui/badge.tsx
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

function Badge({ className, variant = "default", asChild = false, ...props }:
  React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"
  return <Comp data-slot="badge" data-variant={variant} className={cn(badgeVariants({ variant }), className)} {...props} />
}
```

Every badge in the app uses `variant="outline"` plus a caller-supplied color class — a 20px pill (`h-5`, `rounded-4xl`) with 12px `size-3` icons.

### Card

`Card` is a `data-slot`-driven set with a `--card-spacing` custom property (`--spacing(4)`, or `--spacing(3)` at `size="sm"`) that drives padding and gaps consistently across header/content/footer.

```tsx
// frontend/src/components/ui/card.tsx
function Card({ className, size = "default", ...props }) {
  return (
    <div data-slot="card" data-size={size}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) overflow-hidden rounded-xl bg-card py-(--card-spacing) text-sm text-card-foreground ring-1 ring-foreground/10 [--card-spacing:--spacing(4)] has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0 data-[size=sm]:[--card-spacing:--spacing(3)] data-[size=sm]:has-data-[slot=card-footer]:pb-0 *:[img:first-child]:rounded-t-xl *:[img:last-child]:rounded-b-xl",
        className)}
      {...props} />
  )
}

function CardHeader({ className, ...props }) {
  return (
    <div data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-t-xl px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className)}
      {...props} />
  )
}

function CardTitle({ className, ...props }) {
  return <div data-slot="card-title"
    className={cn("font-heading text-base leading-snug font-medium group-data-[size=sm]/card:text-sm", className)} {...props} />
}

function CardDescription({ className, ...props }) {
  return <div data-slot="card-description" className={cn("text-sm text-muted-foreground", className)} {...props} />
}

function CardAction({ className, ...props }) {
  return <div data-slot="card-action" className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)} {...props} />
}

function CardContent({ className, ...props }) {
  return <div data-slot="card-content" className={cn("px-(--card-spacing)", className)} {...props} />
}

function CardFooter({ className, ...props }) {
  return <div data-slot="card-footer"
    className={cn("flex items-center rounded-b-xl border-t bg-muted/50 p-(--card-spacing)", className)} {...props} />
}
```

Cards are separated from the page by a hairline **ring** (`ring-1 ring-foreground/10`), not a border. Adding `className="border-b"` to a `CardHeader` is the app's idiom for a divider under a card title — the `[.border-b]:pb-(--card-spacing)` selector supplies the matching padding.

---

## 10. Client State: `store/use-app-store.ts` (Zustand)

One flat store holds view state, run history, the live event stream, the scoping round, and the pending run action. There is no context provider and no reducer — components select individual slices.

```ts
// frontend/src/store/use-app-store.ts
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
  scoping: { runId: string | null; questions: ScopingQuestion[]
             status: "idle" | "loading" | "ready" | "submitting" | "error"; error: string | null }
  runAction: { runId: string | null; kind: "cancel" | "retry" | null
               status: "idle" | "submitting" | "error"; error: string | null }

  openNewRun: () => void
  showRun: (run: RunRecord) => void
  startHistoryLoad: () => void
  receiveRuns: (runs: RunSummary[]) => void
  failHistoryLoad: (message: string) => void
  connectRunStream: (runId: string) => void
  disconnectRunStream: () => void
  loadScopingQuestions: (runId: string) => Promise<void>
  resumeRun: (runId: string, answers: ScopingAnswers) => Promise<void>
  cancelRun: (runId: string) => Promise<void>
  retryRun: (runId: string) => Promise<void>
}

// A single module-level socket; opening a new one always closes the old.
let activeSocket: WebSocket | null = null

connectRunStream: (runId) => {
  if (activeSocket !== null) { const previous = activeSocket; activeSocket = null; previous.close() }

  set((state) => ({
    streamRunId: runId,
    streamEvents: state.streamRunId === runId ? state.streamEvents : [],
    streamStatus: "connecting",
    streamError: null,
    scoping: scopingStateForRun(state.scoping, runId),
  }))
  const socket = new WebSocket(websocketUrl(runId))   // ws(s)://<host>/ws/runs/<id>
  activeSocket = socket

  socket.onopen = () => { if (activeSocket === socket) set({ streamStatus: "connected" }) }
  socket.onmessage = (message) => {
    if (activeSocket !== socket) return
    let event: WorkflowEvent
    try { event = JSON.parse(message.data) as WorkflowEvent }
    catch { set({ streamStatus: "error", streamError: "The run stream returned invalid JSON" }); return }

    const details = workflowEventDetails(event)
    // Each event appends to the log AND advances the run's phase/status, so the
    // sidebar card and the stage strip update from the same message.
    set((state) => {
      if (state.streamRunId !== runId) return state
      const currentRun = state.currentRun?.run_id === runId
        ? runAfterEvent(state.currentRun, event) : state.currentRun
      return {
        streamEvents: [...state.streamEvents, event],
        currentRun,
        runs: currentRun ? withRunSummary(state.runs, currentRun) : state.runs,
      }
    })
    if (details.runStatus === "paused") void get().loadScopingQuestions(runId)
  }
  socket.onerror = () => { /* streamStatus: "error" */ }
  socket.onclose = () => { /* streamStatus: "disconnected" unless already "error" */ }
}

loadScopingQuestions: async (runId) => {
  // Only an in-flight load short-circuits. A "ready" one must not: every pause
  // is a new round of questions, and skipping the fetch would leave the form
  // showing the previous round's.
  if (current.scoping.runId === runId && current.scoping.status === "loading") return
  // → GET the run's scoping_questions.json artifact, then status: "ready"
}

retryRun: async (runId) => {
  // Retry is a resume with no answers; when the retried run is the selected
  // one, the event log is cleared so the new attempt starts from a blank slate.
}
```

Derivation helpers: `summaryOf(run, duration)` projects a `RunRecord` down to a `RunSummary`; `withRunSummary(runs, run)` upserts it and re-sorts `newestFirst` (descending `started_at`); `runAfterEvent` folds an event's phase/status into the current run; `runAfterResume` keeps a terminal status from being overwritten by a stale resume response.

---

## Data Model Summary

```ts
// frontend/src/lib/api.ts
export type RunStatus = "running" | "paused" | "completed" | "failed" | "cancelled"
export type PickMode = "directory" | "file"
export type RulesMode = "none" | "text" | "file"
export type ArtifactType = "html" | "md" | "xlsx" | "json"
export type ScopingQuestionType = "text" | "single_select" | "multi_select" | "confirm"
export type ScopingAnswerValue = string | string[] | boolean
```

A **`RunSummary`** (sidebar card) contains:

- `run_id: string` — timestamped id, e.g. `20260810-215131-7d550b`; always rendered monospace
- `status: RunStatus` — drives the badge color
- `started_at: string` — ISO timestamp
- `duration: number` — seconds, rendered as `42s` / `3m 5s` / `1h 20m`
- `source_name: string`, `workbook_name: string` — basenames shown as `source → workbook`

A **`RunRecord`** (detail view) contains:

- `run_id`, `status`, `source_name`, `workbook_name` — as above
- `start_time: string` — ISO timestamp
- `workspace_path: string` — absolute host path, truncated monospace with a `title` tooltip
- `phase: string` — backend phase name, mapped to a stage index by `phaseStage`

A **`WorkflowEvent`** is a discriminated union on `type`, all sharing `timestamp: string`:

- `progress` — `phase`, `message`
- `phase_change` — `phase`, `status: "active" | "completed" | "failed"`
- `paused` — `reason`, `questions_artifact`
- `completed` — `final_xlsx`
- `failed` — `error`, optional `reason: "cancelled"`

A **`ScopingQuestion`** contains:

- `id: string` — form field name and answer key
- `question: string` — the prompt text
- `type?: ScopingQuestionType` — defaults to `text`
- `options?: { value: string; label: string }[] | null` — for the two select types

A **`ScopingAnswer`** is `{ value: ScopingAnswerValue; note?: string | null }`, and `ScopingAnswers` is `Record<questionId, ScopingAnswer>`. `ScopingQuestions` (the artifact payload) adds `round: number` and `placeholder_token: string`.

An **`ArtifactSummary`** contains:

- `name: string` — file name, e.g. `review_explorer_v2.html`
- `type: ArtifactType` — chooses the preview mode
- `size: number` — bytes, rendered `B` / `KB` / `MB`
- `path: string` — absolute host path, copyable

A **`CreateRunInput`** contains `source` and `workbook` (absolute paths), `task` (free text), and four nullable fields: `rules_text`, `rules_file`, `scoping_answers`, `review_policy`.

### API surface

All calls are same-origin against the local server; dev runs proxy `/api` to `http://127.0.0.1:8470`.

| Function                          | Call                                                                              |
| --------------------------------- | --------------------------------------------------------------------------------- |
| `pickPath(mode, prompt)`        | `POST /api/pick` → `{ path: string \| null }` (null = operator cancelled) |
| `createRun(input)`              | `POST /api/runs` → `RunRecord`                                           |
| `listRuns()`                    | `GET /api/runs` → `RunSummary[]`                                         |
| `getRun(runId)`                 | `GET /api/runs/{id}` → `RunRecord`                                       |
| `listArtifacts(runId)`          | `GET /api/runs/{id}/artifacts` → `ArtifactSummary[]`                     |
| `artifactUrl(runId, name)`      | `/api/runs/{id}/artifacts/{name}` (iframe src, download href)                   |
| `readArtifactText(runId, name)` | same URL, read as text                                                            |
| `getScopingQuestions(runId)`    | reads the `scoping_questions.json` artifact → `ScopingQuestions`          |
| `resumeRun(runId, answers)`     | `POST /api/runs/{id}/resume` → `RunRecord`                               |
| `cancelRun(runId)`              | `POST /api/runs/{id}/cancel` → `RunRecord`                               |
| live events                       | `WebSocket ws(s)://<host>/ws/runs/{id}` → `WorkflowEvent`                |

Errors are normalized: a non-OK response is thrown as `new Error(body.detail ?? "Request failed with status <code>")`, which is what every inline error string in the UI displays.

---

## Design Tokens (CSS Variables)

The whole palette is `oklch` and, apart from `--destructive`, fully desaturated. Tailwind v4 maps the raw variables to utility namespaces inside `@theme inline`, so `bg-muted`, `text-muted-foreground`, `rounded-xl` etc. all resolve to these values.

```css
/* frontend/src/index.css */
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/geist";

@custom-variant dark (&:is(.dark *));

@theme inline {
    --font-heading: var(--font-sans);
    --font-sans: 'Geist Variable', sans-serif;
    --color-sidebar-ring: var(--sidebar-ring);
    --color-sidebar-border: var(--sidebar-border);
    --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
    --color-sidebar-accent: var(--sidebar-accent);
    --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
    --color-sidebar-primary: var(--sidebar-primary);
    --color-sidebar-foreground: var(--sidebar-foreground);
    --color-sidebar: var(--sidebar);
    --color-chart-5: var(--chart-5);
    --color-chart-4: var(--chart-4);
    --color-chart-3: var(--chart-3);
    --color-chart-2: var(--chart-2);
    --color-chart-1: var(--chart-1);
    --color-ring: var(--ring);
    --color-input: var(--input);
    --color-border: var(--border);
    --color-destructive: var(--destructive);
    --color-accent-foreground: var(--accent-foreground);
    --color-accent: var(--accent);
    --color-muted-foreground: var(--muted-foreground);
    --color-muted: var(--muted);
    --color-secondary-foreground: var(--secondary-foreground);
    --color-secondary: var(--secondary);
    --color-primary-foreground: var(--primary-foreground);
    --color-primary: var(--primary);
    --color-popover-foreground: var(--popover-foreground);
    --color-popover: var(--popover);
    --color-card-foreground: var(--card-foreground);
    --color-card: var(--card);
    --color-foreground: var(--foreground);
    --color-background: var(--background);
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);
    --radius-3xl: calc(var(--radius) * 2.2);
    --radius-4xl: calc(var(--radius) * 2.6);
}

:root {
    --background: oklch(1 0 0);
    --foreground: oklch(0.145 0 0);
    --card: oklch(1 0 0);
    --card-foreground: oklch(0.145 0 0);
    --popover: oklch(1 0 0);
    --popover-foreground: oklch(0.145 0 0);
    --primary: oklch(0.205 0 0);
    --primary-foreground: oklch(0.985 0 0);
    --secondary: oklch(0.97 0 0);
    --secondary-foreground: oklch(0.205 0 0);
    --muted: oklch(0.97 0 0);
    --muted-foreground: oklch(0.556 0 0);
    --accent: oklch(0.97 0 0);
    --accent-foreground: oklch(0.205 0 0);
    --destructive: oklch(0.577 0.245 27.325);
    --border: oklch(0.922 0 0);
    --input: oklch(0.922 0 0);
    --ring: oklch(0.708 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.556 0 0);
    --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);
    --chart-5: oklch(0.269 0 0);
    --radius: 0.625rem;
    --sidebar: oklch(0.985 0 0);
    --sidebar-foreground: oklch(0.145 0 0);
    --sidebar-primary: oklch(0.205 0 0);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.97 0 0);
    --sidebar-accent-foreground: oklch(0.205 0 0);
    --sidebar-border: oklch(0.922 0 0);
    --sidebar-ring: oklch(0.708 0 0);
}

.dark {
    --background: oklch(0.145 0 0);
    --foreground: oklch(0.985 0 0);
    --card: oklch(0.205 0 0);
    --card-foreground: oklch(0.985 0 0);
    --popover: oklch(0.205 0 0);
    --popover-foreground: oklch(0.985 0 0);
    --primary: oklch(0.922 0 0);
    --primary-foreground: oklch(0.205 0 0);
    --secondary: oklch(0.269 0 0);
    --secondary-foreground: oklch(0.985 0 0);
    --muted: oklch(0.269 0 0);
    --muted-foreground: oklch(0.708 0 0);
    --accent: oklch(0.269 0 0);
    --accent-foreground: oklch(0.985 0 0);
    --destructive: oklch(0.704 0.191 22.216);
    --border: oklch(1 0 0 / 10%);
    --input: oklch(1 0 0 / 15%);
    --ring: oklch(0.556 0 0);
    --chart-1: oklch(0.87 0 0);
    --chart-2: oklch(0.556 0 0);
    --chart-3: oklch(0.439 0 0);
    --chart-4: oklch(0.371 0 0);
    --chart-5: oklch(0.269 0 0);
    --sidebar: oklch(0.205 0 0);
    --sidebar-foreground: oklch(0.985 0 0);
    --sidebar-primary: oklch(0.488 0.243 264.376);
    --sidebar-primary-foreground: oklch(0.985 0 0);
    --sidebar-accent: oklch(0.269 0 0);
    --sidebar-accent-foreground: oklch(0.985 0 0);
    --sidebar-border: oklch(1 0 0 / 10%);
    --sidebar-ring: oklch(0.556 0 0);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
    }
  body {
    @apply min-w-80 bg-background text-foreground antialiased;
    }
  html {
    @apply font-sans;
    }
}
```

**Notes for a redesign:**

- A `.dark` block exists and every token has a dark value, but nothing in the app toggles the class today — dark mode is defined, not exposed.
- The status accents (`emerald` / `amber` / `sky` / `red` / `stone`) are **not** tokens; they are literal Tailwind palette classes living in `lib/run-status.ts` and `workflow-progress.tsx`. Any recolor should start there.
- Surface hierarchy is expressed as opacity on one token: page `bg-muted/30`, group panels `bg-muted/18`, footer bars `bg-muted/20`, log body `bg-muted/20`, hover `bg-muted/35`, selected `bg-muted/45`.
- `body` has `min-w-80` (320px), so the layout never collapses below that.

---

## Interaction Patterns

- **View switching** — no router. `openNewRun()` sets `view: "new-run"`; selecting a run fetches its record and sets `view: "run"`. Browser back/forward do nothing.
- **Selection** — the selected sidebar card gets `border-foreground/25 bg-muted/45 shadow-sm` and `aria-current="true"`; hover on the others is `hover:border-foreground/20 hover:bg-muted/35`. Selected artifact rows and the active pipeline stage instead **invert** (`bg-foreground text-background`).
- **Native pickers** — "Choose" round-trips to the OS dialog through the backend. While one dialog is open, the button reads `Choosing…` and *all* pickers in the form are disabled. Cancelling changes nothing.
- **Live streaming** — a WebSocket opens when the run is `running` / `paused` / `failed` and closes on unmount. Each event appends to the log *and* advances the pipeline and the sidebar card in the same `set()`.
- **Auto-scroll** — the log pins to the bottom on every new event via a trailing sentinel `<div ref={end}>` and `scrollIntoView({ block: "end" })`.
- **Pause → resume** — a `paused` event triggers a fetch of that round's questions; the progress card is replaced by the question form. Submitting resumes the run, and the form clears itself when the next round's questions arrive.
- **Optional note beside every choice** — non-text scoping questions render an extra "Add anything the options do not cover" textarea, so an operator is never forced into a wrong option.
- **All-or-nothing validation** — the question form blocks submit until every question is answered, showing one `role="alert"` line rather than per-field errors.
- **Status-exclusive actions** — Cancel appears only while `running`, Retry only when `failed` or `cancelled`. Both show a pending label and surface their error inline.
- **Retry clears the log** — retrying the currently-open run resets `streamEvents` so the new attempt starts from a blank timeline.
- **Artifact preview** — master/detail with a type switch: HTML in an iframe with a 320–900px height range slider plus "Open in new tab", Markdown/JSON as styled text, `.xlsx` as a download panel with a "Copy file path" button that flips its icon to a check on success.
- **Loading and empty states are per-region**, never a full-page spinner: sidebar history, artifact list, artifact preview, and question form each own theirs.
- **Focus visibility** — every custom control carries `focus-visible:ring-2 focus-visible:ring-ring/50` (buttons use `ring-3`); nothing relies on the default outline.
- **Truncation over wrapping** — run ids, paths, and file names truncate with a `title` tooltip; only log messages wrap (`break-words`).
