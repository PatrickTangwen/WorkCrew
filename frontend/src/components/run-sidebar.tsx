import { Plus } from "lucide-react"

import type { RunSummary } from "@/lib/api"
import { formatDuration, formatStartTime } from "@/lib/format"
import { runStatusLabels } from "@/lib/run-status"
import { cn } from "@/lib/utils"

type RunSidebarProps = {
  runs: RunSummary[]
  selectedRunId: string | null
  historyStatus: "idle" | "loading" | "ready" | "error"
  historyError: string | null
  onBrand: () => void
  onNewRun: () => void
  onSelect: (run: RunSummary) => void
}

function RunSidebar({
  runs,
  selectedRunId,
  historyStatus,
  historyError,
  onBrand,
  onNewRun,
  onSelect,
}: RunSidebarProps) {
  return (
    <aside
      aria-label="Run history"
      className="sticky top-0 flex h-svh min-w-0 flex-col border-r border-line bg-shell"
    >
      <button
        type="button"
        onClick={onBrand}
        className="flex cursor-pointer items-baseline gap-px border-b border-line px-[18px] pt-[17px] pb-4 text-left text-xl font-semibold tracking-[-0.035em] focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <span className="text-ink">Work</span>
        <span className="font-normal text-faint">Crew</span>
      </button>

      <div className="px-3.5 pt-3.5 pb-2.5">
        <button
          type="button"
          onClick={onNewRun}
          className="flex h-[38px] w-full cursor-pointer items-center justify-center gap-1.5 rounded-[9px] bg-brand text-[13.5px] font-medium text-white shadow-sm transition-colors hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <Plus className="size-3" strokeWidth={2.5} aria-hidden="true" /> New run
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-2.5 pb-2.5">
        <div className="flex items-center justify-between px-1.5 py-2">
          <span className="font-mono text-[10px] font-semibold tracking-[0.16em] text-faint uppercase">
            Runs
          </span>
          {runs.length > 0 && (
            <span className="font-mono text-[10px] text-ghost">{runs.length}</span>
          )}
        </div>

        {historyStatus === "loading" && runs.length === 0 && (
          <p className="rounded-[10px] border border-dashed border-line-strong px-3 py-3.5 text-xs text-faint">
            Loading run history…
          </p>
        )}
        {historyStatus === "error" && historyError && (
          <p
            role="alert"
            className="mb-2 rounded-[10px] border border-bad-line bg-bad-wash px-3 py-2 text-xs text-bad"
          >
            {historyError}
          </p>
        )}
        {historyStatus === "ready" && runs.length === 0 && (
          <p className="rounded-[10px] border border-dashed border-line-strong px-3 py-3.5 text-xs leading-5 text-faint">
            No runs yet. Start one to create a local history.
          </p>
        )}

        {runs.length > 0 && (
          <ul
            aria-label="Runs"
            className="flex min-h-0 flex-1 flex-col gap-[5px] overflow-y-auto pr-1"
          >
            {runs.map((run) => {
              const selected = run.run_id === selectedRunId
              return (
                <li key={run.run_id}>
                  <button
                    type="button"
                    aria-label={`Open run ${run.run_id}`}
                    aria-current={selected ? "true" : undefined}
                    onClick={() => onSelect(run)}
                    className={cn(
                      "flex w-full cursor-pointer flex-col gap-1 rounded-[10px] border border-transparent p-2.5 text-left transition-colors hover:bg-raise focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      selected && "bg-raise"
                    )}
                  >
                    <span className="block w-full truncate text-[12.5px] font-medium text-ink">
                      {run.source_name} → {run.workbook_name}
                    </span>
                    <span className="flex w-full items-baseline justify-between gap-2">
                      <span className="min-w-0 truncate text-[11px] text-ghost">
                        {runStatusLabels[run.status]} ·{" "}
                        <time dateTime={run.started_at}>
                          {formatStartTime(run.started_at)}
                        </time>
                      </span>
                      <span className="shrink-0 font-mono text-[10.5px] text-ghost">
                        {formatDuration(run.duration)}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-line px-4 py-3.5">
        <span className="inline-flex h-[23px] items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 text-[11px] font-medium text-subtle">
          <span className="size-1.5 rounded-full bg-ok" aria-hidden="true" />
          Local only · no network
        </span>
      </div>
    </aside>
  )
}

export { RunSidebar }
