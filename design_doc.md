# WorkCrew — Full Frontend Component Reference for Redesign

WorkCrew is a **local-first document-to-workbook workflow desk**. An operator picks a folder of source documents and an Excel workbook template, writes a sentence describing the task (optionally pasting screenshots into it), and optionally supplies extraction rules; the backend then runs a multi-stage agent pipeline (Scoping → Filler → Review → Revision → Re-review → Finalize) that fills the workbook and produces auditable artifacts. The workbook's field schema is derived by the scoping pass, not uploaded. The UI is served by a local Python server on loopback and opened in the operator's own browser — there is no cloud, no login, no multi-user state.

**Tech stack**: React 19.2, TypeScript 6, Vite 8, Tailwind CSS v4 (`@theme inline`, no config file), shadcn/ui (only Badge/Button/Card vendored), Radix UI primitives, lucide-react icons, Zustand 5, react-markdown 10, Geist Variable font.

**Styling idiom**: utility classes only. There are **no CSS modules and no styled-components** — every component is styled with Tailwind utilities that resolve to the semantic token set defined in `src/index.css`. `cn()` (clsx + tailwind-merge) merges conditional classes. Component variants use `class-variance-authority` (`cva`).

**Visual character**: near-monochrome. The entire chrome is built from `oklch` greys with `--radius: 0.625rem`; the only saturated colors in the app are the five run-status accents (emerald / amber / sky / red / stone) and `--destructive`. Headings use `font-heading` (aliased to Geist), identifiers and paths use `font-mono`. Surfaces are layered by opacity (`bg-muted/18`, `bg-muted/20`, `bg-muted/30`, `bg-muted/45`) rather than by distinct color values. Cards are separated from the page by a hairline ring (`ring-1 ring-foreground/10`) plus a very soft shadow (`shadow-lg shadow-black/4`), never by a heavy border.

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

### Component tree

```
main (grid)
├── RunSidebar
│   ├── brand block (PanelsTopLeft mark + wordmark + "Local" badge on small screens)
│   ├── Button "New run"
│   ├── ul[aria-label="Runs"] → run cards → RunStatusBadge
│   └── footer Badge "Local only" (lg only)
└── section
    ├── RunCreationForm        (view === "new-run")
    │   └── Card
    │       ├── source folder / workbook pickers
    │       ├── run name input
    │       ├── task textarea + pasted-image thumbnails
    │       ├── rules segmented control (none / text / file)
    │       ├── AgentSettings (<details>)
    │       └── footer bar: status line + "Start run"
    ├── RunDetail              (view === "run")
    │   ├── header Card
    │   ├── ScopingQuestionForm | WorkflowProgress
    │   │   ├── StagePipeline (6 chips)
    │   │   └── LogStream (max-h-64, autoscroll)
    │   └── ArtifactViewer | empty artifacts Card
    └── empty state            (view === "empty")
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
    let ignore = false
    startHistoryLoad()
    void listRuns()
      .then((history) => {
        if (!ignore) receiveRuns(history)
      })
      .catch((cause: unknown) => {
        if (!ignore) {
          failHistoryLoad(
            cause instanceof Error ? cause.message : "Unable to load run history"
          )
        }
      })
    return () => {
      ignore = true
    }
  }, [failHistoryLoad, receiveRuns, startHistoryLoad])

  async function selectRun(run: RunSummary) {
    try {
      showRun(await getRun(run.run_id))
    } catch (cause) {
      failHistoryLoad(
        cause instanceof Error ? cause.message : "Unable to open the selected run"
      )
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

**Empty state anatomy** — a 56px rounded-2xl bordered square holding a `Files` icon, a 3xl heading, a muted one-liner, and a primary button. Vertically centered in the remaining viewport height (the `calc()` accounts for the collapsed top bar below `lg`).

---

## 2. Left Rail: `run-sidebar.tsx`

The persistent run history. Three visual zones separated by hairline borders: brand header → New-run action → scrollable run list, with a pinned "Local only" footer on large screens.

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

function formatDuration(seconds: number) {
  const totalSeconds = Math.max(0, Math.floor(seconds))
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const remainingSeconds = totalSeconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

function formatStartTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value))
}

function RunSidebar({
  runs, selectedRunId, historyStatus, historyError, onNewRun, onSelect,
}: RunSidebarProps) {
  return (
    <aside
      aria-label="Run history"
      className="flex min-w-0 flex-col border-b bg-background lg:min-h-svh lg:border-r lg:border-b-0"
    >
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

      <div className="p-3 lg:p-4">
        <Button onClick={onNewRun} className="w-full">
          <Plus /> New run
        </Button>
      </div>

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

**Run card anatomy** (three rows inside a `rounded-xl border p-3` button):

1. `run_id` in mono semibold (truncating) + `RunStatusBadge` pushed right.
2. `source_name → workbook_name` in 12px medium, truncating.
3. Localized start time (`Intl.DateTimeFormat`, e.g. "Aug 11, 2:05 PM") + a `Clock3` icon with humanized duration (`45s` / `3m 12s` / `1h 04m`), both 11px muted.

**Selected state**: `border-foreground/25 bg-muted/45 shadow-sm` plus `aria-current="true"`. Hover is a lighter version of the same idea (`hover:border-foreground/20 hover:bg-muted/35`). Empty and loading states are dashed-border placeholder blocks; the error state is a `bg-destructive/8` pill.

---

## 3. New Run Form: `run-creation-form.tsx`

Six stacked field groups inside one Card, each a `rounded-xl border bg-muted/18 p-3` panel with a title + `Required`/`Optional` micro-caps tag + one-line explanation. The card footer is a `bg-muted/20` bar with a live status line on the left and the submit button on the right.

```tsx
// frontend/src/components/run-creation-form.tsx
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { FileSpreadsheet, Folder, Play, X } from "lucide-react"

import { AgentSettings } from "@/components/agent-settings"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  createRun, listAgentOptions, pickPath, readTaskImage, SUPPORTED_IMAGE_TYPES,
  type AgentOption, type AgentSelection, type CreateRunInput, type PickMode,
  type RulesMode, type RunRecord, type TaskImageUpload,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type PathKey = "source" | "workbook"

/** A pasted image: what the operator sees, and what the API takes. */
type TaskImage = { preview: string; upload: TaskImageUpload }

const paths = [
  { key: "source",   label: "Source folder", description: "Documents the workflow will read", mode: "directory", icon: Folder },
  { key: "workbook", label: "Workbook",      description: "Excel template to fill",           mode: "file",      icon: FileSpreadsheet },
]

const rulesModes = [
  { mode: "none", label: "No rules" },
  { mode: "text", label: "Describe them" },
  { mode: "file", label: "Use a text file" },
]

function RunCreationForm({ onCreated }: { onCreated: (run: RunRecord) => void }) {
  const [values, setValues] = useState<Record<PathKey, string>>({ source: "", workbook: "" })
  const [task, setTask] = useState("")
  const [name, setName] = useState("")
  const [rulesMode, setRulesMode] = useState<RulesMode>("none")
  const [rulesText, setRulesText] = useState("")
  const [rulesFile, setRulesFile] = useState("")
  const [pickingKey, setPickingKey] = useState<PathKey | "rules" | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentOptions, setAgentOptions] = useState<AgentOption[]>([])
  const [agentOptionsStatus, setAgentOptionsStatus] =
    useState<"loading" | "ready" | "error">("loading")
  const [agentOptionsError, setAgentOptionsError] = useState<string | null>(null)
  const [agents, setAgents] = useState<Record<string, AgentSelection>>({})
  const [images, setImages] = useState<TaskImage[]>([])
  const agentOptionsRequestRef = useRef(0)

  // Object URLs back the thumbnails. Removing one image revokes its own
  // URL; the rest are revoked when the form goes away. Keying this on
  // `images` would revoke the URLs of thumbnails still on screen.
  const imagesRef = useRef(images)
  imagesRef.current = images
  useEffect(() => () => {
    for (const image of imagesRef.current) URL.revokeObjectURL(image.preview)
  }, [])

  async function addPastedImages(files: File[]) {
    const supported = files.filter((file) => SUPPORTED_IMAGE_TYPES.includes(file.type))
    if (supported.length === 0) return
    setError(null)
    const added = await Promise.all(
      supported.map(async (file) => ({
        preview: URL.createObjectURL(file),
        upload: await readTaskImage(file),
      }))
    )
    setImages((current) => [...current, ...added])
  }

  function removeImage(index: number) {
    setImages((current) => {
      URL.revokeObjectURL(current[index].preview)
      return current.filter((_, position) => position !== index)
    })
  }

  const loadAgentSettings = useCallback(async () => {
    const request = ++agentOptionsRequestRef.current
    setAgentOptionsStatus("loading")
    setAgentOptionsError(null)
    try {
      const options = await listAgentOptions()
      if (request !== agentOptionsRequestRef.current) return
      setAgentOptions(options)
      setAgentOptionsStatus("ready")
    } catch (cause) {
      if (request !== agentOptionsRequestRef.current) return
      setAgentOptionsError(
        cause instanceof Error ? cause.message : "Unable to load agent settings"
      )
      setAgentOptionsStatus("error")
    }
  }, [])

  useEffect(() => {
    // The server owns the roles, defaults and effort vocabularies. Do not
    // silently run with defaults when that contract could not be loaded.
    void loadAgentSettings()
    return () => { agentOptionsRequestRef.current += 1 }
  }, [loadAgentSettings])

  const chosenAgents = Object.fromEntries(
    Object.entries(agents).filter(
      ([, selection]) => selection.model !== null || selection.effort !== null
    )
  )

  const ready =
    Boolean(values.source) &&
    Boolean(values.workbook) &&
    task.trim().length > 0 &&
    agentOptionsStatus === "ready" &&
    (rulesMode !== "text" || rulesText.trim().length > 0) &&
    (rulesMode !== "file" || Boolean(rulesFile))

  async function choose(key: PathKey | "rules", mode: PickMode, prompt: string) {
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
      name: name.trim() || null,
      // Only what the operator actually chose; the server resolves the
      // rest against its own pinned defaults.
      agents: Object.keys(chosenAgents).length > 0 ? chosenAgents : null,
      task_images: images.map((image) => image.upload),
      rules_text: rulesMode === "text" ? rulesText.trim() : null,
      rules_file: rulesMode === "file" ? rulesFile : null,
      scoping_answers: null,
      review_policy: null,
    }
    try {
      onCreated(await createRun(input))
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

          {/* ── 1. Path pickers, two-up on sm and wider ───────────────── */}
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {paths.map((field) => {
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
                        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                          Required
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">{field.description}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div
                      title={value || undefined}
                      className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                    >
                      {value || "Nothing selected"}
                    </div>
                    <Button
                      size="sm" variant="outline" type="button"
                      disabled={pickingKey !== null}
                      onClick={() => void choose(field.key, field.mode, `Choose ${field.label.toLowerCase()}`)}
                    >
                      {pickingKey === field.key ? "Choosing…" : "Choose"}
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>

          {/* ── 2. Run name (optional) ────────────────────────────────── */}
          <CardContent>
            <div role="group" aria-label="Run name input" className="rounded-xl border bg-muted/18 p-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Run name</p>
                <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  Optional
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Names the run, so its id reads as more than a timestamp.
              </p>
              <input
                aria-label="Run name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. charity 2015 review"
                className="mt-3 w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Without a name, the source folder names the run.
              </p>
            </div>
          </CardContent>

          {/* ── 3. Task + pasted images ───────────────────────────────── */}
          <CardContent>
            <div role="group" aria-label="Task input" className="rounded-xl border bg-muted/18 p-3">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Task</p>
                <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  Required
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                What should this run produce? The workbook schema is derived from
                this. Paste screenshots straight into the box — the agents read
                them with your words.
              </p>
              <textarea
                aria-label="Task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                onPaste={(event) => {
                  const files = Array.from(event.clipboardData.files)
                  if (files.length === 0) return
                  // Keep the pasted image out of the text box itself.
                  event.preventDefault()
                  void addPastedImages(files)
                }}
                rows={4}
                placeholder="e.g. Fill one row per charity folder from the annual reports, keyed by registration number."
                className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />

              {images.length > 0 && (
                <ul aria-label="Task images" className="mt-3 flex flex-wrap gap-2">
                  {images.map((image, index) => (
                    <li key={image.preview} className="relative">
                      <img
                        src={image.preview}
                        alt={`Task image ${index + 1}`}
                        className="size-20 rounded-lg border object-cover"
                      />
                      <button
                        type="button"
                        aria-label={`Remove task image ${index + 1}`}
                        onClick={() => removeImage(index)}
                        className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border bg-background text-xs shadow-sm hover:bg-muted"
                      >
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>

          {/* ── 4. Rules: segmented control + conditional editor ──────── */}
          <CardContent>
            <div role="group" aria-label="Rules input" className="rounded-xl border bg-muted/18 p-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">Rules</p>
                    <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                      Optional
                    </span>
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
                  <div
                    title={rulesFile || undefined}
                    className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                  >
                    {rulesFile || "Nothing selected"}
                  </div>
                  <Button
                    size="sm" variant="outline" type="button"
                    disabled={pickingKey !== null}
                    onClick={() => void choose("rules", "file", "Choose rules file")}
                  >
                    {pickingKey === "rules" ? "Choosing…" : "Choose"}
                  </Button>
                </div>
              )}
            </div>
          </CardContent>

          {/* ── 5. Agents (loading / ready / error) ───────────────────── */}
          <CardContent>
            {agentOptionsStatus === "ready" ? (
              <AgentSettings
                options={agentOptions}
                selections={agents}
                onChange={(role, selection) =>
                  setAgents((current) => ({ ...current, [role]: selection }))
                }
              />
            ) : agentOptionsStatus === "loading" ? (
              <p className="text-sm text-muted-foreground" role="status">
                Loading agent settings…
              </p>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-3">
                <p className="text-sm text-destructive" role="alert">{agentOptionsError}</p>
                <Button type="button" size="sm" variant="outline" onClick={() => void loadAgentSettings()}>
                  Retry agent settings
                </Button>
              </div>
            )}
          </CardContent>

          {/* ── 6. Footer bar ─────────────────────────────────────────── */}
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

### Behaviours a redesign must preserve

- **Path pickers are not file inputs.** `Choose` posts to `/api/pick`, which opens the *host OS* native chooser; the returned absolute path is shown in a read-only mono chip that truncates with a `title` tooltip. While a chooser is open, *all* Choose buttons disable (`pickingKey !== null`) and the active one reads `Choosing…`.
- **Screenshots paste into the task box.** `onPaste` intercepts `clipboardData.files`, calls `preventDefault()` so the image never lands in the textarea, filters to `SUPPORTED_IMAGE_TYPES`, and appends 80px `object-cover` thumbnails below the textarea. Each thumbnail has a 20px circular remove button overhanging its top-right corner (`-top-1.5 -right-1.5`). Previews are object URLs, revoked individually on removal and en masse on unmount.
- **Agent settings gate readiness.** If `/api/agents` fails, the form is *not* submittable — `ready` requires `agentOptionsStatus === "ready"`. The error state is a destructive-tinted panel with a `Retry agent settings` button. Stale responses are discarded via a monotonically increasing request ref.
- **Only explicit agent choices are sent.** `chosenAgents` filters out roles where both `model` and `effort` are `null`; if nothing was changed, `agents: null` goes over the wire and the server applies its pinned defaults.
- **The footer status line is the only validation surface** — there are no per-field error messages. It is `aria-live="polite"` and swaps between the muted hint, the ready message, and a destructive error.

---

## 4. Agent Settings: `agent-settings.tsx`

A native `<details>` disclosure, collapsed by default, holding one row per pipeline role. The summary carries a right-aligned counter that reads `Defaults` or `N changed`.

```tsx
// frontend/src/components/agent-settings.tsx
import type { AgentOption, AgentSelection } from "@/lib/api"

const ROLE_LABELS: Record<string, string> = {
  scoping: "Scoping",
  filler: "Filler",
  revision: "Revision",
  reviewer: "Review",
  re_review: "Re-review",
}

type AgentSettingsProps = {
  options: AgentOption[]
  selections: Record<string, AgentSelection>
  onChange: (role: string, selection: AgentSelection) => void
}

/** Per-role model and reasoning effort, collapsed until asked for. */
function AgentSettings({ options, selections, onChange }: AgentSettingsProps) {
  if (options.length === 0) return null

  const changed = options.filter((option) => {
    const selection = selections[option.role]
    return Boolean(selection?.model) || Boolean(selection?.effort)
  }).length

  return (
    <details className="rounded-xl border bg-muted/18 p-3">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        Agents
        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Optional
        </span>
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {changed === 0 ? "Defaults" : `${changed} changed`}
        </span>
      </summary>

      <p className="mt-2 text-xs text-muted-foreground">
        Model and reasoning effort per role. Leave a field alone to keep the
        pinned default.
      </p>

      <div className="mt-3 grid gap-2">
        {options.map((option) => {
          const selection = selections[option.role] ?? { model: null, effort: null }
          const modelListId = `models-${option.role}`
          return (
            <div
              key={option.role}
              role="group"
              aria-label={`${ROLE_LABELS[option.role] ?? option.role} agent`}
              className="grid gap-2 rounded-lg border bg-background p-2.5 sm:grid-cols-[8rem_minmax(0,1fr)_9rem] sm:items-center"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {ROLE_LABELS[option.role] ?? option.role}
                </p>
                <p className="font-mono text-[10px] text-muted-foreground">{option.runtime}</p>
              </div>

              <input
                aria-label={`${ROLE_LABELS[option.role] ?? option.role} model`}
                list={modelListId}
                value={selection.model ?? ""}
                placeholder={option.model}
                onChange={(event) =>
                  onChange(option.role, { ...selection, model: event.target.value.trim() || null })
                }
                className="min-w-0 rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
              <datalist id={modelListId}>
                {option.model_suggestions.map((model) => (
                  <option key={model} value={model} />
                ))}
              </datalist>

              <select
                aria-label={`${ROLE_LABELS[option.role] ?? option.role} effort`}
                value={selection.effort ?? ""}
                onChange={(event) =>
                  onChange(option.role, { ...selection, effort: event.target.value || null })
                }
                className="rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              >
                <option value="">
                  {option.effort ? `Default (${option.effort})` : "Default"}
                </option>
                {option.effort_choices.map((level) => (
                  <option key={level} value={level}>{level}</option>
                ))}
              </select>
            </div>
          )
        })}
      </div>
    </details>
  )
}

export { AgentSettings, ROLE_LABELS }
```

**Row layout**: `sm:grid-cols-[8rem_minmax(0,1fr)_9rem]` — a fixed label column (role name + runtime in 10px mono), a flexible model combobox (free-text `<input list>` backed by a `<datalist>` of suggestions; the server default shows as the *placeholder*, so an empty field means "keep the default"), and a fixed effort `<select>` whose first option reads `Default (high)`. Below `sm` the three cells stack.

---

## 5. Run Detail: `run-detail.tsx`

Composes the three stacked cards and owns the WebSocket lifecycle for the selected run.

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
  const streamRunId = useAppStore((state) => state.streamRunId)
  const streamEvents = useAppStore((state) => state.streamEvents)
  const connectRunStream = useAppStore((state) => state.connectRunStream)
  const disconnectRunStream = useAppStore((state) => state.disconnectRunStream)
  const scoping = useAppStore((state) => state.scoping)
  const resumeRun = useAppStore((state) => state.resumeRun)
  const cancelRun = useAppStore((state) => state.cancelRun)
  const retryRun = useAppStore((state) => state.retryRun)
  const runAction = useAppStore((state) => state.runAction)
  const events = streamRunId === run.run_id ? streamEvents : []
  const streamable =
    run.status === "running" || run.status === "paused" || run.status === "failed"
  const streamLifecycle =
    run.status === "failed" ? "failed" : streamable ? "active" : "inactive"

  useEffect(() => {
    if (!streamable) return
    connectRunStream(run.run_id)
    return disconnectRunStream
  }, [connectRunStream, disconnectRunStream, run.run_id, streamLifecycle, streamable])

  const action = runAction.runId === run.run_id ? runAction : null
  const actionPending = action?.status === "submitting"

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4">
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
                aria-label="Cancel run" variant="outline" size="sm"
                disabled={actionPending}
                className="text-destructive hover:bg-destructive/8"
                onClick={() => void cancelRun(run.run_id)}
              >
                <Ban /> {actionPending ? "Cancelling…" : "Cancel"}
              </Button>
            )}
            {(run.status === "failed" || run.status === "cancelled") && (
              <Button
                aria-label="Retry run" size="sm"
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

**Header card layout**: `sm:grid-cols-[minmax(0,1fr)_auto]`. Left column = status badge + mono run id on one row, then a truncating 2xl `font-heading` title `source → workbook`. Right column = right-aligned metadata (start time with a `Clock3` icon, workspace path in mono with a `title` tooltip), then the single contextual action button, then any action error in destructive 12px.

**Action affordances by status** — `running` → outline `Cancel` tinted destructive on hover; `failed` / `cancelled` → primary `Retry`; `paused` / `completed` → no button (the scoping form or artifact viewer is the action). Buttons swap their label to a present-participle while pending.

---

## 6. Stage Pipeline + Log Stream: `workflow-progress.tsx`

```tsx
// frontend/src/components/workflow-progress.tsx
import { useEffect, useMemo, useRef } from "react"
import { Check, Circle, LoaderCircle, X } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { RunRecord, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

const stages = ["Scoping", "Filler", "Review", "Revision", "Re-review", "Finalize"]

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

function stageStatuses(run: RunRecord, events: WorkflowEvent[]): StageStatus[] {
  if (
    run.status === "completed" ||
    events.some((event) => workflowEventDetails(event).runStatus === "completed")
  ) {
    return stages.map(() => "completed")
  }

  const phaseEvent = [...events]
    .reverse()
    .map(workflowEventDetails)
    .find((event) => event.phaseStatus !== null)
  const phase = phaseEvent?.phase ?? run.phase
  const current = phaseStage[phase] ?? 0
  const failed =
    run.status === "failed" ||
    events.some((event) => workflowEventDetails(event).runStatus === "failed") ||
    phaseEvent?.phaseStatus === "failed"
  const currentStatus: StageStatus = failed
    ? "failed"
    : phaseEvent?.phaseStatus === "completed"
      ? "completed"
      : "active"

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

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" })
  }, [events])

  return (
    <div
      aria-label="Run log"
      aria-live="polite"
      className="max-h-64 overflow-y-auto rounded-xl border bg-muted/20"
    >
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
                <span
                  className={cn(
                    "min-w-0 break-words",
                    (details.error !== null || details.phaseStatus === "failed") && "text-destructive"
                  )}
                >
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

**Pipeline visual**: six equal chips, `1 → 3 → 6` columns across breakpoints (never a connector-line stepper — they are independent bordered pills, each `rounded-xl px-3 py-3` with a 14px icon and a 12px medium label). The *active* chip is the only inverted surface in the app (`bg-foreground text-background`) and spins a `LoaderCircle`. Completed = emerald tint, failed = red tint, pending = plain background with muted text.

**Log stream**: a bordered `bg-muted/20` scroll region capped at `max-h-64`, rows `divide-y font-mono text-xs`, each row a fixed-width `HH:MM:SS` timestamp plus a wrapping message. Failure rows turn `text-destructive`. A sentinel `<div>` at the end is scrolled into view on every event batch. The engine's own failure text is *also* surfaced above the log as a destructive panel so it is visible without scrolling.

### Event → UI mapping (`lib/workflow-events.ts`)

One pure function normalizes the five event shapes into what the UI needs, so no component branches on `event.type`.

```ts
// frontend/src/lib/workflow-events.ts
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
    return { phase: event.phase, phaseStatus: null, runStatus: null, logMessage: event.message, error: null }
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
    return { phase: null, phaseStatus: null, runStatus: "paused", logMessage: event.reason, error: null }
  }
  if (event.type === "completed") {
    return {
      phase: "FINALIZE", phaseStatus: null, runStatus: "completed",
      logMessage: `Run completed: ${event.final_xlsx}`, error: null,
    }
  }
  if (event.reason === "cancelled") {
    return { phase: null, phaseStatus: null, runStatus: "cancelled", logMessage: event.error, error: null }
  }
  return { phase: null, phaseStatus: null, runStatus: "failed", logMessage: event.error, error: event.error }
}

export { workflowEventDetails }
```

Note the distinction: a *cancelled* run carries `error: null`, so it renders as an ordinary muted log line, not as a red failure panel.

---

## 7. Scoping Questions: `scoping-question-form.tsx`

Replaces the progress card whenever `status === "paused"`. Four question types dispatch through a lookup table of control components; every non-text question also gets an optional free-text note.

```tsx
// frontend/src/components/scoping-question-form.tsx
import { useEffect, useState, type ComponentType, type FormEvent } from "react"
import { CircleHelp, Send } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type {
  ScopingAnswers, ScopingAnswerValue, ScopingQuestion, ScopingQuestionType,
} from "@/lib/api"

type FormStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type Choice = {
  key: string
  value: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}

function ChoiceList({
  questionId, inputType, choices,
}: { questionId: string; inputType: "radio" | "checkbox"; choices: Choice[] }) {
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

function answered(answer: ScopingAnswerValue | undefined) {
  if (Array.isArray(answer)) return answer.length > 0
  if (typeof answer === "string") return answer.trim().length > 0
  return typeof answer === "boolean"
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

// SingleSelectQuestion → ChoiceList with radios, checked={answer === option.value}
// MultiSelectQuestion  → ChoiceList with checkboxes over a string[] answer
// ConfirmQuestion      → ChoiceList with radios over a fixed Yes/No pair (boolean answer)

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

  function setValue(id: string, value: ScopingAnswerValue) {
    setValues((current) => ({ ...current, [id]: value }))
    setValidationError(null)
  }

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

                  {type !== "text" && (
                    <label className="mt-3 block">
                      <span className="text-xs text-muted-foreground">
                        Add anything the options do not cover (optional)
                      </span>
                      <textarea
                        aria-label={`Note for ${question.question}`}
                        value={notes[question.id] ?? ""}
                        onChange={(event) =>
                          setNotes((current) => ({ ...current, [question.id]: event.target.value }))
                        }
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

**Question anatomy**: a real `<fieldset>` on `bg-muted/18` with a `<legend>` carrying a mono index number then the question text. Choices render two-up on `sm+` as full-width bordered `<label>` rows with a native radio/checkbox — the whole row is the hit target. Validation is all-or-nothing at submit time, surfaced as one destructive line above the right-aligned submit button.

**Multi-round**: the same component is reused for round 2, 3, … — the `useEffect` keyed on `questions` clears all local answers so the previous round's input never leaks forward.

---

## 8. Artifact Viewer: `artifact-viewer.tsx`

Two-pane browser: a fixed 17rem list on the left, a preview pane on the right. Only a curated set of artifacts is shown, in a fixed presentation order.

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

function userFacingArtifacts(items: ArtifactSummary[]) {
  const byName = new Map(items.map((artifact) => [artifact.name, artifact]))
  const finalReview = byName.has("review_explorer_v2.html")
    ? "review_explorer_v2.html"
    : "review_explorer.html"
  const finalReviewZh = byName.has("review_explorer_zh_v2.html")
    ? "review_explorer_zh_v2.html"
    : "review_explorer_zh.html"
  const displayOrder = [
    "final.xlsx",
    "human_review.md",
    finalReview,
    finalReviewZh,
    "run_summary.md",
    "evaluation.md",
  ]

  return displayOrder.flatMap((name) => {
    const artifact = byName.get(name)
    return artifact ? [artifact] : []
  })
}

function TextArtifactPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setText(null)
    setError(null)
    void readArtifactText(runId, artifact.name)
      .then((content) => { if (!cancelled) setText(content) })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Unable to read artifact")
      })
    return () => { cancelled = true }
  }, [artifact.name, runId])

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

  useEffect(() => setCopyStatus("idle"), [artifact.name])

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
          <a
            href={url} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-4"
          >
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

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(artifact.path)
      setCopyStatus("copied")
    } catch {
      setCopyStatus("failed")
    }
  }

  return (
    <div className="grid min-h-56 place-items-center rounded-xl border border-dashed bg-muted/18 p-6 text-center">
      <div>
        <Download className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 font-medium">Final workbook</p>
        <p className="mt-1 max-w-lg truncate font-mono text-xs text-muted-foreground" title={artifact.path}>
          {artifact.path}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <a
            href={url} download={artifact.name}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/88"
            aria-label={`Download ${artifact.name}`}
          >
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

  useEffect(() => {
    let cancelled = false
    setArtifacts(null)
    setSelectedName(null)
    setError(null)
    void listArtifacts(runId)
      .then((items) => {
        if (cancelled) return
        const visibleItems = userFacingArtifacts(items)
        setArtifacts(visibleItems)
        setError(null)
        setSelectedName((current) =>
          visibleItems.some((artifact) => artifact.name === current)
            ? current
            : (visibleItems[0]?.name ?? null)
        )
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Unable to list artifacts")
        }
      })
    return () => { cancelled = true }
  }, [runId])

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
                    <Badge
                      variant="outline"
                      className={cn("uppercase", artifact.name === selectedName && "border-background/35 text-background")}
                    >
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

### Curation rule

The backend writes many intermediate files; the viewer shows **only six**, always in this order: `final.xlsx`, `human_review.md`, the review explorer (preferring the `_v2` variant when present), its Chinese counterpart, `run_summary.md`, `evaluation.md`. Anything else in the run workspace is hidden from the operator. Missing entries are simply skipped, so the list is variable-length.

### Preview modes by `artifact.type`

| type | preview |
|---|---|
| `html` | sandboxed-looking `<iframe>` on a white background, with a **range slider** (320–900px, step 20) controlling its height and a mono readout, plus an "Open in new tab" link |
| `md` | `react-markdown` rendered inside an `<article>` whose typography comes entirely from arbitrary child selectors (`[&_h1]:…`, `[&_pre]:…`) — there is no `@tailwindcss/typography` plugin |
| `json` | raw text in a `bg-muted` `<pre>` block |
| `xlsx` | not previewable: a dashed-border drop-zone-styled panel with a big `Download` glyph, the absolute path in mono, a primary download anchor, and a "Copy file path" button that flips its icon to `Check` for the copied state |

**List item anatomy**: 16px `File` icon, then a two-line stack (truncating filename in 14px medium, size via `formatBytes` in 11px mono at 65% opacity), then an uppercase outline `Badge` with the type. The selected row inverts to `bg-foreground text-background`, and the badge's border/text flip to `background/35` so it stays legible on the dark row.

---

## 9. Status Badge: `run-status-badge.tsx` + `lib/run-status.ts`

A single presentation table drives every status surface, so the five states are never re-described inline.

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
import { Ban, CheckCircle2, CirclePause, LoaderCircle, TriangleAlert, type LucideIcon } from "lucide-react"
import type { RunStatus } from "@/lib/api"

type RunStatusPresentation = {
  label: string
  badgeClassName: string
  dotClassName: string
  detailTitle: string
  detailDescription: string
  detailIcon: LucideIcon
  detailIconClassName: string
}

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

export { runStatusPresentation }
```

Badge shape: 20px tall, fully rounded (`rounded-4xl`), a 6px status dot, then the label. `running` is the only animated one (`animate-pulse` dot). The `detail*` fields exist in the table for status surfaces beyond the badge.

---

## 10. UI Primitives (`components/ui/`)

Only three shadcn components are vendored. Everything else is hand-written markup.

### Button

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

Note `type = "button"` by default — submit buttons must opt in explicitly. Icons are auto-sized to 16px by the `[&_svg]:size-4` selector, so call sites write `<Plus />` with no className.

### Badge

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

function Badge({ className, variant = "default", asChild = false, ...props }) {
  const Comp = asChild ? Slot.Root : "span"
  return <Comp data-slot="badge" data-variant={variant} className={cn(badgeVariants({ variant }), className)} {...props} />
}
```

Every badge in WorkCrew uses `variant="outline"` and overrides the colors via `className`. Badge icons are 12px.

### Card

Cards are driven by a `--card-spacing` custom property (16px default, 12px at `size="sm"`), which every sub-slot consumes for its padding. That is why `CardHeader className="border-b"` picks up bottom padding automatically — the `[.border-b]:pb-(--card-spacing)` selector.

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

function CardHeader({ className, ...props }) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 rounded-t-xl px-(--card-spacing) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }) {
  return (
    <div
      data-slot="card-title"
      className={cn("font-heading text-base leading-snug font-medium group-data-[size=sm]/card:text-sm", className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }) {
  return <div data-slot="card-description" className={cn("text-sm text-muted-foreground", className)} {...props} />
}

function CardContent({ className, ...props }) {
  return <div data-slot="card-content" className={cn("px-(--card-spacing)", className)} {...props} />
}

function CardFooter({ className, ...props }) {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center rounded-b-xl border-t bg-muted/50 p-(--card-spacing)", className)}
      {...props}
    />
  )
}
```

`CardAction` also exists (right-aligned slot in the header grid) but is currently unused.

---

## 11. Client State: `store/use-app-store.ts` (Zustand)

One flat store. No middleware, no persistence — reloading the page re-fetches history from the local server.

```ts
type AppView = "empty" | "new-run" | "run"
type ScopingStatus = "idle" | "loading" | "ready" | "submitting" | "error"

type ScopingState = {
  runId: string | null
  questions: ScopingQuestion[]
  status: ScopingStatus
  error: string | null
}

type RunActionState = {
  runId: string | null
  kind: "cancel" | "retry" | null
  status: "idle" | "submitting" | "error"
  error: string | null
}

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
  scoping: ScopingState
  runAction: RunActionState
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
```

### The live stream

A **module-level `activeSocket`** guarantees exactly one open WebSocket. Every callback checks `activeSocket === socket` before writing state, so a socket that lost the race can never clobber the current run's view.

```ts
function websocketUrl(runId: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runs/${encodeURIComponent(runId)}`
}

connectRunStream: (runId) => {
  if (activeSocket !== null) {
    const previous = activeSocket
    activeSocket = null
    previous.close()
  }

  set((state) => ({
    streamRunId: runId,
    streamEvents: state.streamRunId === runId ? state.streamEvents : [],
    streamStatus: "connecting",
    streamError: null,
    scoping: scopingStateForRun(state.scoping, runId),
  }))
  const socket = new WebSocket(websocketUrl(runId))
  activeSocket = socket

  socket.onopen = () => { if (activeSocket === socket) set({ streamStatus: "connected" }) }
  socket.onmessage = (message) => {
    if (activeSocket !== socket) return
    let event: WorkflowEvent
    try {
      event = JSON.parse(message.data) as WorkflowEvent
    } catch {
      set({ streamStatus: "error", streamError: "The run stream returned invalid JSON" })
      return
    }

    const details = workflowEventDetails(event)

    set((state) => {
      if (state.streamRunId !== runId) return state
      const currentRun =
        state.currentRun?.run_id === runId
          ? runAfterEvent(state.currentRun, event)
          : state.currentRun
      return {
        streamEvents: [...state.streamEvents, event],
        currentRun,
        runs: currentRun ? withRunSummary(state.runs, currentRun) : state.runs,
      }
    })
    if (details.runStatus === "paused") {
      void get().loadScopingQuestions(runId)
    }
  }
  socket.onerror = () => {
    if (activeSocket === socket) {
      set({ streamStatus: "error", streamError: "Run stream connection failed" })
    }
  }
  socket.onclose = () => {
    if (activeSocket === socket) {
      activeSocket = null
      set((state) => ({
        streamStatus: state.streamStatus === "error" ? "error" : "disconnected",
      }))
    }
  }
}
```

Each event mutates three things at once: the appended log, the live `currentRun` (phase + status), and the matching sidebar summary — which is why the sidebar card's badge changes in real time while the run detail is open.

### Derivation helpers

```ts
function summaryOf(run: RunRecord, duration = 0): RunSummary {
  return {
    run_id: run.run_id, status: run.status, started_at: run.start_time,
    duration, source_name: run.source_name, workbook_name: run.workbook_name,
  }
}

function newestFirst(runs: RunSummary[]) {
  return [...runs].sort((left, right) => right.started_at.localeCompare(left.started_at))
}

function withRunSummary(runs: RunSummary[], run: RunRecord) {
  const existing = runs.find((item) => item.run_id === run.run_id)
  return newestFirst([
    summaryOf(run, existing?.duration),
    ...runs.filter((item) => item.run_id !== run.run_id),
  ])
}

function runAfterEvent(run: RunRecord, event: WorkflowEvent) {
  const details = workflowEventDetails(event)
  return { ...run, phase: details.phase ?? run.phase, status: details.runStatus ?? run.status }
}

function runAfterResume(current: RunRecord | null, resumed: RunRecord) {
  if (current?.run_id !== resumed.run_id) return current
  if (["completed", "failed", "cancelled"].includes(current.status)) return current
  return { ...resumed, phase: current.phase }
}
```

Sorting is always newest-first by ISO `started_at` string comparison.

### Scoping rounds

`loadScopingQuestions` short-circuits **only** on an in-flight load, never on a `ready` one — each pause is a *new round* of questions, and skipping the fetch would leave the form showing the previous round's. `retryRun` reuses the resume endpoint with an empty answer map and clears the stream so the log restarts clean.

---

## Data Model Summary

Everything the UI renders comes from these types (`lib/api.ts`). Mock data for a redesign should match these shapes.

```ts
export type PickMode = "directory" | "file"

export type RunStatus = "running" | "paused" | "completed" | "failed" | "cancelled"

export type RunSummary = {
  run_id: string          // e.g. "20260811-140512-charity-2015-review"
  status: RunStatus
  started_at: string      // ISO 8601
  duration: number        // seconds
  source_name: string     // folder basename
  workbook_name: string   // xlsx basename
}

export type RunRecord = {
  run_id: string
  status: RunStatus
  start_time: string      // ISO 8601
  workspace_path: string  // absolute path
  phase: string           // e.g. "CLAUDE_FILL"
  source_name: string
  workbook_name: string
}

export type WorkflowEvent =
  | { timestamp: string; type: "progress";     phase: string; message: string }
  | { timestamp: string; type: "phase_change"; phase: string; status: "active" | "completed" | "failed" }
  | { timestamp: string; type: "paused";       reason: string; questions_artifact: string }
  | { timestamp: string; type: "completed";    final_xlsx: string }
  | { timestamp: string; type: "failed";       error: string; reason?: "cancelled" }

export type ScopingQuestionType = "text" | "single_select" | "multi_select" | "confirm"

export type ScopingQuestion = {
  id: string
  question: string
  type?: ScopingQuestionType            // defaults to "text"
  options?: { value: string; label: string }[] | null
}

export type ScopingAnswerValue = string | string[] | boolean

/** The chosen value, plus whatever the operator wanted to add beside it. */
export type ScopingAnswer = { value: ScopingAnswerValue; note?: string | null }

export type ScopingAnswers = Record<string, ScopingAnswer>

export type ScopingQuestions = {
  round: number
  placeholder_token: string
  questions: ScopingQuestion[]
}

export type ArtifactType = "html" | "md" | "xlsx" | "json"

export type ArtifactSummary = {
  name: string   // "final.xlsx"
  type: ArtifactType
  size: number   // bytes
  path: string   // absolute path on the operator's machine
}

export type RulesMode = "none" | "text" | "file"

export type AgentRole = "scoping" | "filler" | "revision" | "reviewer" | "re_review"

/** What the operator may choose for one role, and its defaults. */
export type AgentOption = {
  role: AgentRole
  runtime: string             // e.g. "claude_code" | "codex"
  model: string               // server default, shown as placeholder
  model_suggestions: string[] // datalist entries
  effort: string | null       // server default effort, if any
  effort_choices: string[]    // e.g. ["low", "medium", "high"]
}

export type AgentSelection = { model: string | null; effort: string | null }

/** An image pasted into the task description, carried as content. */
export type TaskImageUpload = { content_type: string; data: string }  // data is base64

export const SUPPORTED_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"]

export type CreateRunInput = {
  source: string
  workbook: string
  task: string
  name: string | null
  agents: Record<string, AgentSelection> | null
  task_images: TaskImageUpload[]
  rules_text: string | null
  rules_file: string | null
  scoping_answers: string | null
  review_policy: string | null
}
```

### API surface

| call | endpoint |
|---|---|
| `pickPath(mode, prompt)` | `POST /api/pick` → `{ path: string \| null }` (null = operator cancelled the native chooser) |
| `listAgentOptions()` | `GET /api/agents` → `AgentOption[]` |
| `createRun(input)` | `POST /api/runs` → `RunRecord` |
| `listRuns()` | `GET /api/runs` → `RunSummary[]` |
| `getRun(runId)` | `GET /api/runs/{id}` → `RunRecord` |
| `listArtifacts(runId)` | `GET /api/runs/{id}/artifacts` → `ArtifactSummary[]` |
| `artifactUrl(runId, name)` | `GET /api/runs/{id}/artifacts/{name}` (raw bytes; also the `iframe`/download src) |
| `readArtifactText(runId, name)` | same URL, read as text |
| `getScopingQuestions(runId)` | artifact `scoping_questions.json` → `ScopingQuestions` |
| `resumeRun(runId, answers)` | `POST /api/runs/{id}/resume` → `RunRecord` |
| `cancelRun(runId)` | `POST /api/runs/{id}/cancel` → `RunRecord` |
| live events | `WS /ws/runs/{id}` → a stream of `WorkflowEvent` |

Errors are normalized: a non-OK response is parsed as `{ detail?: string }` and thrown as `new Error(detail ?? "Request failed with status N")`, which is what every red message in the UI displays.

```ts
async function responseError(response: Response) {
  const body = (await response.json()) as { detail?: string }
  return new Error(body.detail ?? `Request failed with status ${response.status}`)
}

async function readResponse<T>(response: Response) {
  if (response.ok) return (await response.json()) as T
  throw await responseError(response)
}

/** Read a pasted image into the base64 payload the API takes. */
export async function readTaskImage(file: File) {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ""
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return { content_type: file.type, data: btoa(binary) }
}
```

---

## Design Tokens (CSS Variables)

The whole file is `src/index.css` — there is no `tailwind.config.js`. Tailwind v4's `@theme inline` maps semantic color/radius names onto the raw custom properties below.

```css
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
  * { @apply border-border outline-ring/50; }
  body { @apply min-w-80 bg-background text-foreground antialiased; }
  html { @apply font-sans; }
}
```

**Notes for a redesign**

- The `.dark` block exists but **nothing toggles it** — there is no theme switcher, and `<html>` never gets the `dark` class. The app ships light-only today.
- `--radius: 0.625rem` (10px) is the base; `rounded-lg` = 10px, `rounded-xl` = 14px, `rounded-2xl` = 18px, `rounded-4xl` = 26px (used for pill badges).
- Every neutral is fully desaturated `oklch(L 0 0)`. The only chroma in the base palette is `--destructive`.
- Status accents are **plain Tailwind palette classes**, not tokens: `emerald-50/200/500/700`, `amber-*`, `sky-*`, `red-*`, `stone-*`. A redesign that introduces a token for status color would need to touch `lib/run-status.ts` and `workflow-progress.tsx`'s `statusStyle`.
- `min-w-80` on `<body>` is the hard floor for narrow windows.
- Font stack: a single variable font (Geist) serves both `font-sans` and `font-heading`; `font-mono` falls back to the Tailwind default mono stack (run ids, paths, sizes, timestamps, model names).

### Spacing / sizing conventions observed

| context | value |
|---|---|
| main pane padding | `p-5` → `sm:p-8` → `lg:p-10` |
| card stack gap (run detail) | `gap-4` |
| field panel | `rounded-xl border bg-muted/18 p-3` |
| inner control | `rounded-lg border bg-background px-3 py-2 text-sm` |
| path chip | `rounded-md border px-2.5 py-2 font-mono text-xs` |
| icon tile | `size-9 rounded-lg` (brand mark, field icons) |
| micro-caps tag | `text-[10px] font-medium tracking-wide uppercase text-muted-foreground` |
| section eyebrow | `text-xs font-semibold tracking-[0.18em] uppercase` |
| page title | `font-heading text-3xl font-semibold tracking-tight` |
| focus ring | `focus:ring-2 focus:ring-ring/20` (inputs) / `focus-visible:ring-2 ring-ring/50` (buttons) |

---

## Interaction Patterns

1. **Native OS choosers, not web file inputs.** Paths are absolute strings from the host machine. Buttons show `Choosing…` and every picker disables while one chooser is open.
2. **Paste-to-attach.** Screenshots pasted into the task textarea become base64 uploads with 80px thumbnails; the text box never receives the image.
3. **Progressive disclosure.** Rules editors appear only for the matching segmented-control mode; agent settings live in a collapsed `<details>` that reports `Defaults` / `N changed` without being opened.
4. **Live WebSocket stream.** Opened for `running` / `paused` / `failed` runs, closed on unmount or status change. Exactly one socket at a time. Log auto-scrolls to the newest line.
5. **Status drives the layout.** `paused` swaps the progress card for the question form; `completed` swaps the empty artifacts card for the two-pane viewer; `running` shows Cancel; `failed`/`cancelled` shows Retry.
6. **Multi-round scoping.** The question form resets on every new `questions` array, so round 2 starts blank.
7. **Optimistic in-place updates.** Every event updates the run detail *and* its sidebar card at once; there is no polling and no refresh button.
8. **Errors are inline and local.** Sidebar errors, form footer errors, action errors, artifact errors, and stream errors each render next to their own surface — there are no toasts, modals, or a global error banner anywhere in the app.
9. **Accessibility conventions to keep**: `role="group"` + `aria-label` per field panel, `aria-live="polite"` on the form status line / log / preview pane, `aria-current` on the selected run, `role="radiogroup"` + `role="radio"` + `aria-checked` on the rules segmented control, real `<fieldset>`/`<legend>` for scoping questions, and `aria-label` on every icon-only control.
