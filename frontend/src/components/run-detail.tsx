import { useEffect, useMemo, useState } from "react"

import { ArtifactViewer } from "@/components/artifact-viewer"
import { EventLogDialog } from "@/components/event-log-dialog"
import { ScopingQuestionForm } from "@/components/scoping-question-form"
import { TopBar, TopBarButton } from "@/components/top-bar"
import { WorkflowProgress } from "@/components/workflow-progress"
import type { RunRecord } from "@/lib/api"
import { formatDuration, formatStartTime } from "@/lib/format"
import { pipelineView } from "@/lib/pipeline"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/store/use-app-store"

const artifactHints: Record<string, string> = {
  failed: "This run produced none.",
  cancelled: "This run was cancelled early.",
}

/**
 * How long a run has been going, or how long it ran for. A run that stopped
 * without recording an ending cannot be measured, and says so rather than
 * counting up forever.
 */
function runDuration(startTime: string, finishedAt: string | null, live: boolean) {
  const started = Date.parse(startTime)
  const finished =
    finishedAt !== null
      ? Date.parse(finishedAt)
      : live
        ? Date.now()
        : Number.NaN
  if (Number.isNaN(started) || Number.isNaN(finished)) return null
  return Math.max(0, finished - started) / 1000
}

/** Re-renders once a second so a live run's clock keeps moving. */
function useSecondHand(running: boolean) {
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => setTick((count) => count + 1), 1000)
    return () => clearInterval(timer)
  }, [running])
}

function RunDetail({ run }: { run: RunRecord }) {
  const eventsRunId = useAppStore((state) => state.eventsRunId)
  const runEvents = useAppStore((state) => state.runEvents)
  const eventsError = useAppStore((state) => state.eventsError)
  const loadRunEvents = useAppStore((state) => state.loadRunEvents)
  const connectRunStream = useAppStore((state) => state.connectRunStream)
  const disconnectRunStream = useAppStore((state) => state.disconnectRunStream)
  const loadScopingQuestions = useAppStore((state) => state.loadScopingQuestions)
  const scoping = useAppStore((state) => state.scoping)
  const resumeRun = useAppStore((state) => state.resumeRun)
  const cancelRun = useAppStore((state) => state.cancelRun)
  const retryRun = useAppStore((state) => state.retryRun)
  const runAction = useAppStore((state) => state.runAction)
  const [logOpen, setLogOpen] = useState(false)

  const events = useMemo(
    () => (eventsRunId === run.run_id ? runEvents : []),
    [eventsRunId, run.run_id, runEvents]
  )
  // Only a running engine has new events to stream. A paused run may have
  // been reopened after a server restart, so its durable log and questions
  // are the source of truth until the operator resumes it.
  const streamable = run.status === "running"

  useEffect(() => {
    if (!streamable) {
      void loadRunEvents(run.run_id)
      if (run.status === "paused") void loadScopingQuestions(run.run_id)
      return
    }
    connectRunStream(run.run_id)
    return disconnectRunStream
  }, [
    connectRunStream,
    disconnectRunStream,
    loadRunEvents,
    loadScopingQuestions,
    run.run_id,
    run.status,
    streamable,
  ])

  const pipeline = pipelineView(run, events)
  const live = pipeline.status === "running" || pipeline.status === "paused"
  useSecondHand(live)

  const duration = runDuration(run.start_time, pipeline.finishedAt, live)

  const action = runAction.runId === run.run_id ? runAction : null
  const actionPending = action?.status === "submitting"

  return (
    <>
      <TopBar
        title={
          <span className="truncate text-sm font-medium text-ink">
            {run.source_name} → {run.workbook_name}
          </span>
        }
      >
        {pipeline.status === "running" && (
          <TopBarButton
            aria-label="Cancel run"
            disabled={actionPending}
            onClick={() => void cancelRun(run.run_id)}
            className="border-bad-line bg-bad-wash text-bad hover:bg-bad-surface"
          >
            {actionPending ? "Cancelling…" : "Cancel run"}
          </TopBarButton>
        )}
        {(pipeline.status === "failed" || pipeline.status === "cancelled") && (
          <TopBarButton
            aria-label="Retry run"
            disabled={actionPending}
            onClick={() => void retryRun(run.run_id)}
            className="border-line-dash text-ink"
          >
            {actionPending ? "Retrying…" : "Retry run"}
          </TopBarButton>
        )}
        <TopBarButton onClick={() => setLogOpen(true)}>
          <span
            aria-hidden="true"
            className={cn(
              "size-[5px] rounded-full",
              live ? "animate-wc-pulse bg-ok" : "bg-line-dash"
            )}
          />
          Event log
          <span className="font-mono text-[11px] text-ghost">{events.length}</span>
        </TopBarButton>
      </TopBar>

      <div className="mx-auto flex w-full max-w-[1000px] flex-1 flex-col gap-[18px] px-4 pt-6 pb-10 sm:px-6 lg:px-8 lg:pt-[30px] lg:pb-12">
        <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:gap-6">
          <div className="w-full min-w-0">
            <h1 className="truncate text-[28px] leading-[1.2] font-semibold tracking-[-0.02em] text-ink">
              {run.source_name} → {run.workbook_name}
            </h1>
            <p
              title={run.workspace_path}
              className="mt-2 truncate font-mono text-[11.5px] text-faint"
            >
              {run.workspace_path}
            </p>
          </div>
          <div className="flex shrink-0 flex-col gap-[5px] text-left sm:text-right">
            <span className="text-[11.5px] text-faint">
              Started{" "}
              <time dateTime={run.start_time}>{formatStartTime(run.start_time)}</time>
            </span>
            <span className="font-mono text-base font-medium text-ink">
              {duration === null ? "—" : formatDuration(duration)}
            </span>
            <span className="font-mono text-[11px] text-ghost">{run.phase}</span>
          </div>
        </div>

        <WorkflowProgress pipeline={pipeline} runId={run.run_id} />

        {run.status === "paused" && (
          <ScopingQuestionForm
            questions={scoping.runId === run.run_id ? scoping.questions : []}
            status={scoping.runId === run.run_id ? scoping.status : "loading"}
            error={scoping.runId === run.run_id ? scoping.error : null}
            onSubmit={(answers) => void resumeRun(run.run_id, answers)}
          />
        )}

        {pipeline.failure !== null && (
          <div className="rounded-xl border border-bad-line bg-bad-wash px-4 py-4">
            <p className="text-[12.5px] font-medium text-bad">
              {pipeline.stages[pipeline.current]?.name ?? "The run"} stage stopped
            </p>
            <p className="mt-1.5 font-mono text-xs leading-[1.6] text-pretty text-bad-ink">
              {pipeline.failure}
            </p>
          </div>
        )}

        {action?.status === "error" && action.error && (
          <p role="alert" className="text-xs text-bad">
            {action.error}
          </p>
        )}

        {pipeline.status === "completed" ? (
          <ArtifactViewer runId={run.run_id} />
        ) : (
          <div className="flex items-center gap-3 rounded-xl border border-dashed border-line-strong bg-shell p-5">
            <span className="grid size-[30px] shrink-0 place-items-center rounded-lg border border-line bg-surface font-mono text-[8.5px] font-medium text-ghost">
              OUT
            </span>
            <p className="text-[12.5px] text-faint">
              Artifacts appear here as the workflow advances.{" "}
              {artifactHints[pipeline.status] ?? "Draft workbook is being written."}
            </p>
          </div>
        )}
      </div>

      {logOpen && (
        <EventLogDialog
          events={events}
          error={eventsError}
          live={live}
          onClose={() => setLogOpen(false)}
        />
      )}
    </>
  )
}

export { RunDetail }
