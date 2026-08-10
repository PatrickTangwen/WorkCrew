import { useEffect } from "react"
import { Clock3, FolderOpen, PackageOpen } from "lucide-react"

import { ArtifactViewer } from "@/components/artifact-viewer"
import { RunStatusBadge } from "@/components/run-status-badge"
import { WorkflowProgress } from "@/components/workflow-progress"
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
  const events = streamRunId === run.run_id ? streamEvents : []
  const streamable =
    run.status === "running" || run.status === "paused" || run.status === "failed"

  useEffect(() => {
    if (!streamable) return
    connectRunStream(run.run_id)
    return disconnectRunStream
  }, [connectRunStream, disconnectRunStream, run.run_id, streamable])

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
          <div className="grid gap-1 text-xs text-muted-foreground sm:text-right">
            <span className="flex items-center gap-1.5 sm:justify-end">
              <Clock3 className="size-3.5" />
              Started {new Date(run.start_time).toLocaleString()}
            </span>
            <span className="max-w-md truncate font-mono" title={run.workspace_path}>
              {run.workspace_path}
            </span>
          </div>
        </CardContent>
      </Card>

      <WorkflowProgress run={run} events={events} />

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
