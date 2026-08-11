import { useEffect, useRef } from "react"

import type { WorkflowEvent } from "@/lib/api"
import { formatClock } from "@/lib/format"
import { phaseStage, STAGES } from "@/lib/pipeline"
import { cn } from "@/lib/utils"
import { workflowEventDetails } from "@/lib/workflow-events"

/** The whole record for one run, in arrival order. */
function EventLogDialog({
  events,
  error,
  live,
  onClose,
}: {
  events: WorkflowEvent[]
  error?: string | null
  /** Whether more events can still arrive, which changes what "empty" means. */
  live?: boolean
  onClose: () => void
}) {
  const list = useRef<HTMLUListElement>(null)

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [onClose])

  useEffect(() => {
    const element = list.current
    if (element !== null) element.scrollTop = element.scrollHeight
  }, [events])

  let stage = 0

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-40 grid place-items-center bg-ink/32 p-10"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Event log"
        onClick={(event) => event.stopPropagation()}
        className="flex max-h-full w-[min(760px,100%)] flex-col overflow-hidden rounded-[14px] border border-line-strong bg-surface shadow-[0_18px_44px_rgba(31,30,28,.22)]"
      >
        <div className="flex items-center justify-between gap-3 border-b border-line-soft px-5 py-3.5">
          <p className="text-[13px] font-medium text-ink">Event log</p>
          <button
            type="button"
            onClick={onClose}
            className="h-7 cursor-pointer rounded-[7px] border border-line-strong bg-surface px-2.5 text-[11.5px] font-medium text-subtle transition-colors hover:bg-shell focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            Close
          </button>
        </div>

        {error ? (
          <p role="alert" className="px-5 py-8 text-center text-sm text-bad">
            {error}
          </p>
        ) : events.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-faint">
            {live
              ? "Waiting for workflow events…"
              : "This run recorded no events."}
          </p>
        ) : (
          <ul ref={list} className="min-h-0 flex-1 overflow-y-auto py-1.5">
            {events.map((event, index) => {
              const details = workflowEventDetails(event)
              // Events that name no phase belong to whichever stage was running.
              stage = details.phase === null ? stage : (phaseStage[details.phase] ?? stage)
              const failed =
                details.error !== null || details.phaseStatus === "failed"
              return (
                <li
                  key={`${event.timestamp}-${index}`}
                  className="flex items-baseline gap-3.5 px-5 py-2"
                >
                  <time
                    dateTime={event.timestamp}
                    className="w-[58px] shrink-0 font-mono text-[10.5px] text-ghost"
                  >
                    {formatClock(event.timestamp)}
                  </time>
                  <span
                    className={cn(
                      "w-[74px] shrink-0 font-mono text-[9.5px] font-medium tracking-[0.07em] uppercase",
                      failed ? "text-bad" : "text-ghost"
                    )}
                  >
                    {STAGES[stage]}
                  </span>
                  <span
                    className={cn(
                      "min-w-0 text-xs leading-[1.5] text-pretty",
                      failed ? "text-bad-ink" : "text-body"
                    )}
                  >
                    {details.logMessage}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

export { EventLogDialog }
