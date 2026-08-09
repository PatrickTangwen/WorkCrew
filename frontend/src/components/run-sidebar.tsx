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
  runs,
  selectedRunId,
  historyStatus,
  historyError,
  onNewRun,
  onSelect,
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
