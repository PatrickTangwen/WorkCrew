import { Clock3, FolderOpen, PackageOpen } from "lucide-react"

import { ArtifactViewer } from "@/components/artifact-viewer"
import { RunStatusBadge } from "@/components/run-status-badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { RunRecord } from "@/lib/api"
import { runStatusPresentation } from "@/lib/run-status"

function RunDetail({ run }: { run: RunRecord }) {
  const status = runStatusPresentation[run.status]
  const StatusIcon = status.detailIcon
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

      <Card className="min-h-72 bg-background">
        <CardHeader className="border-b">
          <CardTitle>Workflow status</CardTitle>
          <CardDescription>{status.detailDescription}</CardDescription>
        </CardHeader>
        <CardContent className="grid min-h-48 place-items-center">
          <div className="text-center">
            <div className="mx-auto grid size-14 place-items-center rounded-2xl border bg-muted/45">
              <StatusIcon
                className={`size-6 ${status.detailIconClassName}`}
                aria-hidden="true"
              />
            </div>
            <p className="mt-4 text-sm font-medium">{status.detailTitle}</p>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{run.phase}</p>
          </div>
        </CardContent>
      </Card>

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
