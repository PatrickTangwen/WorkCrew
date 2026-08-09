import { Badge } from "@/components/ui/badge"
import type { RunStatus } from "@/lib/api"
import { cn } from "@/lib/utils"
import { runStatusPresentation } from "@/lib/run-status"

function RunStatusBadge({ status }: { status: RunStatus }) {
  const presentation = runStatusPresentation[status]
  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5", presentation.badgeClassName)}
    >
      <span className={cn("size-1.5 rounded-full", presentation.dotClassName)} />
      {presentation.label}
    </Badge>
  )
}

export { RunStatusBadge }
