import { useEffect } from "react"
import { Ban, Clock3, FolderOpen, PackageOpen, RotateCcw } from "lucide-react"

import { ArtifactViewer } from "@/components/artifact-viewer"
import { RunStatusBadge } from "@/components/run-status-badge"
import { ScopingQuestionForm } from "@/components/scoping-question-form"
import { WorkflowProgress } from "@/components/workflow-progress"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
              <p role="alert" className="max-w-sm text-xs text-destructive">
                {action.error}
              </p>
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
