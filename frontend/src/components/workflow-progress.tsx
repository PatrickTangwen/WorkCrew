import { useEffect, useMemo, useRef } from "react"
import { Check, Circle, LoaderCircle, X } from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { RunRecord, WorkflowEvent } from "@/lib/api"
import { workflowEventDetails } from "@/lib/workflow-events"

const stages = ["Scoping", "Filler", "Review", "Revision", "Re-review", "Finalize"]

const phaseStage: Record<string, number> = {
  INITIALIZING: 0,
  INIT: 0,
  PREPARE_WORKSPACE: 0,
  BUILD_MANIFEST: 0,
  LOAD_SCHEMA: 0,
  CLAUDE_SCOPE: 0,
  AWAIT_SCOPING_ANSWERS: 0,
  CLAUDE_FILL: 1,
  VALIDATE: 1,
  WRITE_DRAFT: 1,
  CODEX_REVIEW: 2,
  CLAUDE_REVISE: 3,
  APPLY_ALLOWED_REVISIONS: 3,
  CODEX_REREVIEW: 4,
  HUMAN_REVIEW: 4,
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
  pending: "border-border bg-background text-muted-foreground",
  active: "border-foreground/25 bg-foreground text-background shadow-sm",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-red-200 bg-red-50 text-red-700",
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
    <ol
      aria-label="Workflow stages"
      className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6"
    >
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
          <span className="[&_svg]:size-3.5">
            <StageIcon status={statuses[index]} />
          </span>
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
        <p className="px-4 py-6 text-sm text-muted-foreground">
          Waiting for workflow events…
        </p>
      ) : (
        <ul className="divide-y font-mono text-xs">
          {events.map((event, index) => {
            const details = workflowEventDetails(event)
            return (
              <li
                key={`${event.timestamp}-${index}`}
                className="flex gap-3 px-4 py-2.5"
              >
                <time
                  dateTime={event.timestamp}
                  className="shrink-0 text-muted-foreground"
                >
                  {new Date(event.timestamp).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })}
                </time>
                <span
                  className={cn(
                    "min-w-0 break-words",
                    (details.error !== null || details.phaseStatus === "failed") &&
                      "text-destructive"
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
  const failure = [...events]
    .reverse()
    .map(workflowEventDetails)
    .find((event) => event.error !== null)
  return (
    <Card className="min-h-72 bg-background">
      <CardHeader className="border-b">
        <CardTitle>Workflow progress</CardTitle>
        <CardDescription>
          Live engine stages and timestamped progress messages.
        </CardDescription>
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
