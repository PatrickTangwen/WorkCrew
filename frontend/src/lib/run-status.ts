import {
  Ban,
  CheckCircle2,
  CirclePause,
  LoaderCircle,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react"

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
