import { useEffect, useState } from "react"

import { ThinkingOrb } from "@/components/thinking-orb"
import { formatClock, formatDuration } from "@/lib/format"
import {
  stageStatePresentation,
  stageSummary,
  type PipelineView,
  type StageState,
  type StageView,
} from "@/lib/pipeline"
import { cn } from "@/lib/utils"

/** The bar under the card title: one segment per stage, filled as they land. */
const trackClass: Record<StageState, string> = {
  completed: "bg-ink",
  active: "bg-brand animate-wc-pulse",
  waiting: "bg-brand/60",
  failed: "bg-bad",
  stopped: "bg-line",
  pending: "bg-line",
}

function StageMarker({ state }: { state: StageState }) {
  if (state === "completed") {
    return (
      <span className="grid size-4 place-items-center rounded-full bg-ink">
        <span className="h-[2.5px] w-[5.5px] -translate-y-px rotate-[-45deg] border-b-[1.25px] border-l-[1.25px] border-surface" />
      </span>
    )
  }
  if (state === "active") {
    return (
      <span className="box-border size-4 rounded-full border-[1.25px] border-brand bg-[linear-gradient(to_right,var(--brand)_50%,transparent_50%)]" />
    )
  }
  if (state === "waiting") {
    return (
      <span className="box-border grid size-4 place-items-center rounded-full border-[1.5px] border-brand/55">
        <span className="size-[4.5px] rounded-full bg-brand" />
      </span>
    )
  }
  if (state === "failed") {
    return (
      <span className="box-border grid size-4 place-items-center rounded-full bg-bad font-mono text-[8px] font-medium text-surface">
        ✕
      </span>
    )
  }
  if (state === "stopped") {
    return (
      <span className="box-border grid size-4 place-items-center rounded-full border-[1.25px] border-line-dash font-mono text-[8px] font-medium text-ghost">
        –
      </span>
    )
  }
  return <span className="box-border size-4 rounded-full border-[1.25px] border-line-strong" />
}

function StageCell({
  stage,
  selected,
  onSelect,
}: {
  stage: StageView
  selected: boolean
  onSelect: () => void
}) {
  const presentation = stageStatePresentation[stage.state]
  return (
    <li data-status={stage.state} aria-label={`${stage.name}: ${stage.state}`}>
      <button
        type="button"
        aria-pressed={selected}
        onClick={onSelect}
        className={cn(
          "flex w-full min-w-0 cursor-pointer flex-col gap-[5px] rounded-[9px] border px-2.5 py-[9px] text-left focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
          selected ? "border-line-dash bg-shell" : "border-line-soft bg-transparent"
        )}
      >
        <span className="flex w-full min-w-0 items-center gap-1.5">
          <span className="grid size-[18px] shrink-0 place-items-center">
            <StageMarker state={stage.state} />
          </span>
          <span
            className={cn(
              "truncate text-[11.5px] font-medium",
              stage.state === "pending" ? "text-ghost" : "text-ink"
            )}
          >
            {stage.name}
          </span>
        </span>
        <span className="flex w-full flex-nowrap items-baseline justify-between gap-1.5">
          <span
            className={cn(
              "shrink-0 font-mono text-[9.5px] font-medium tracking-[0.06em] uppercase",
              presentation.className
            )}
          >
            {presentation.word}
          </span>
          <span className="font-mono text-[10.5px] text-ghost">
            {stage.duration === null ? "—" : formatDuration(stage.duration)}
          </span>
        </span>
      </button>
    </li>
  )
}

/**
 * The stage under the fold: its headline, and the events it produced. The
 * headline shimmers only while that stage is the one doing work.
 */
function StageDetail({ stage, headline }: { stage: StageView; headline: string }) {
  const presentation = stageStatePresentation[stage.state]
  const active = stage.state === "active"
  return (
    <div className="mt-4 border-t border-line-soft pt-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <p className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
          {active && <ThinkingOrb state="shaping" size={16} />}
          {active ? (
            <span className="animate-wc-shimmer bg-[linear-gradient(100deg,var(--ghost)_0%,var(--ghost)_38%,var(--ink)_50%,var(--ghost)_62%,var(--ghost)_100%)] bg-[length:220%_100%] bg-clip-text text-transparent">
              {headline}
            </span>
          ) : (
            <span>{headline}</span>
          )}
        </p>
        <p
          className={cn(
            "shrink-0 font-mono text-[9.5px] font-medium tracking-[0.06em] uppercase",
            presentation.className
          )}
        >
          {presentation.word} ·{" "}
          {stage.duration === null ? "—" : formatDuration(stage.duration)}
        </p>
      </div>

      {stage.entries.length > 0 ? (
        // The stage's own slice of the record. The event log holds all of it.
        <ul className="mt-2.5 ml-0.5 flex max-h-52 flex-col overflow-y-auto border-l border-line-strong pl-3">
          {stage.entries.map((entry, index) => (
            <li
              key={`${entry.timestamp}-${index}`}
              className="flex items-baseline gap-3 py-[3px]"
            >
              <time
                dateTime={entry.timestamp}
                className="w-[54px] shrink-0 font-mono text-[10.5px] text-ghost"
              >
                {formatClock(entry.timestamp)}
              </time>
              <span
                className={cn(
                  "min-w-0 text-[11.5px] leading-[1.5] text-pretty",
                  entry.failed ? "text-bad-ink" : "text-body"
                )}
              >
                {entry.message}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1.5 text-xs leading-[1.6] text-pretty text-subtle">
          {stageSummary[stage.state]}
        </p>
      )}
    </div>
  )
}

/** The six-stage pipeline, with whichever stage the operator is reading. */
function WorkflowProgress({
  pipeline,
  runId,
}: {
  pipeline: PipelineView
  runId: string
}) {
  const [selected, setSelected] = useState<number | null>(null)

  // Opening another run starts from that run's own stage, not the last one read.
  useEffect(() => setSelected(null), [runId])

  const focus = selected ?? Math.min(pipeline.current, pipeline.stages.length - 1)
  const stage = pipeline.stages[focus]
  const latest = stage.entries[stage.entries.length - 1]
  const headline =
    focus === pipeline.current && latest
      ? `${stage.name} — ${latest.message}`
      : stage.name

  return (
    <div className="rounded-[14px] border border-line bg-surface p-5 shadow-[0_1px_3px_rgba(31,30,28,.05)]">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[13px] font-medium text-ink">Pipeline</p>
        <p className="font-mono text-[11px] text-faint">
          {pipeline.current >= pipeline.stages.length
            ? `${pipeline.stages.length} of ${pipeline.stages.length} complete`
            : `step ${pipeline.current + 1} of ${pipeline.stages.length}`}
        </p>
      </div>

      <div aria-hidden="true" className="mt-3 flex gap-[3px]">
        {pipeline.stages.map((item) => (
          <span
            key={item.name}
            className={cn("h-1.5 flex-1 rounded-[3px]", trackClass[item.state])}
          />
        ))}
      </div>

      <ul
        aria-label="Workflow stages"
        className="mt-2.5 grid grid-cols-[repeat(auto-fit,minmax(146px,1fr))] gap-1.5"
      >
        {pipeline.stages.map((item, index) => (
          <StageCell
            key={item.name}
            stage={item}
            selected={index === focus}
            onSelect={() => setSelected(index)}
          />
        ))}
      </ul>

      <StageDetail stage={stage} headline={headline} />
    </div>
  )
}

export { WorkflowProgress }
