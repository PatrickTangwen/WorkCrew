import { ChevronLeft, ChevronRight } from "lucide-react"

import type { AgentOption, AgentSelection } from "@/lib/api"
import { cn } from "@/lib/utils"

const ROLE_LABELS: Record<string, string> = {
  scoping: "Scoping",
  filler: "Filler",
  revision: "Revision",
  reviewer: "Review",
  re_review: "Re-review",
}

type AgentsMenuProps = {
  options: AgentOption[]
  selections: Record<string, AgentSelection>
  /** The role whose detail pane is open, or null for the role list. */
  openRole: string | null
  onOpenRole: (role: string | null) => void
  onChange: (role: string, selection: AgentSelection) => void
}

const rowClass =
  "flex h-8 w-full cursor-pointer items-center justify-between gap-2.5 whitespace-nowrap rounded-lg px-2.5 text-left text-xs font-medium text-ink transition-colors hover:bg-line-soft focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"

const sectionLabel =
  "font-mono text-[9px] font-semibold tracking-[0.14em] text-ghost uppercase"

function labelFor(role: string) {
  return ROLE_LABELS[role] ?? role
}

/** One role's model and reasoning effort. Empty means "keep the pinned default". */
function AgentDetail({
  option,
  selection,
  onBack,
  onChange,
}: {
  option: AgentOption
  selection: AgentSelection
  onBack: () => void
  onChange: (selection: AgentSelection) => void
}) {
  const label = labelFor(option.role)
  const models = [
    { value: "", label: `Default · ${option.model}` },
    ...option.model_suggestions.map((model) => ({ value: model, label: model })),
  ]
  const efforts = [
    { value: "", label: "Default" },
    ...option.effort_choices.map((level) => ({ value: level, label: level })),
  ]

  return (
    <div className="flex flex-col gap-[7px] px-1 pt-[3px] pb-[5px]">
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-label="Back to agents"
          onClick={onBack}
          className="grid size-[22px] shrink-0 cursor-pointer place-items-center rounded-[7px] border border-line-strong bg-shell text-body transition-colors hover:bg-raise hover:text-ink focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ChevronLeft className="size-3" aria-hidden="true" />
        </button>
        <span className="min-w-0 flex-1 text-xs font-medium text-ink">{label}</span>
        <span className="shrink-0 font-mono text-[9.5px] text-ghost">
          {option.runtime}
        </span>
      </div>

      <div className="flex flex-col gap-1">
        <span className={sectionLabel}>Model</span>
        <div role="radiogroup" aria-label={`${label} model`} className="flex flex-col gap-0.5">
          {models.map((model) => {
            const chosen = (selection.model ?? "") === model.value
            return (
              <button
                key={model.value || "default"}
                type="button"
                role="radio"
                aria-checked={chosen}
                onClick={() => onChange({ ...selection, model: model.value || null })}
                className={cn(
                  "flex h-7 cursor-pointer items-center justify-between gap-2.5 rounded-[7px] px-2.5 text-left font-mono text-[11px] whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                  chosen ? "bg-line-soft text-ink" : "text-body hover:bg-line-soft/60"
                )}
              >
                {model.label}
                <span aria-hidden="true" className={cn("font-mono", !chosen && "opacity-0")}>
                  ✓
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <span className={sectionLabel}>Thinking level</span>
        {/* A runtime may offer more levels than fit on one line, so they wrap. */}
        <div
          role="radiogroup"
          aria-label={`${label} effort`}
          className="flex flex-wrap gap-1"
        >
          {efforts.map((level) => {
            const chosen = (selection.effort ?? "") === level.value
            return (
              <button
                key={level.value || "default"}
                type="button"
                role="radio"
                aria-checked={chosen}
                onClick={() => onChange({ ...selection, effort: level.value || null })}
                className={cn(
                  "h-[26px] min-w-[52px] flex-1 cursor-pointer rounded-[7px] border px-1.5 text-[11px] font-medium whitespace-nowrap transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                  chosen
                    ? "border-ink bg-ink text-surface"
                    : "border-line-strong bg-paper text-body hover:bg-shell"
                )}
              >
                {level.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/** The agents popover: roles first, one role's settings on the way in. */
function AgentsMenu({
  options,
  selections,
  openRole,
  onOpenRole,
  onChange,
}: AgentsMenuProps) {
  const opened = options.find((option) => option.role === openRole)

  if (opened) {
    return (
      <AgentDetail
        option={opened}
        selection={selections[opened.role] ?? { model: null, effort: null }}
        onBack={() => onOpenRole(null)}
        onChange={(selection) => onChange(opened.role, selection)}
      />
    )
  }

  return (
    <>
      {options.map((option) => {
        const selection = selections[option.role]
        const touched = Boolean(selection?.model) || Boolean(selection?.effort)
        return (
          <button
            key={option.role}
            type="button"
            onClick={() => onOpenRole(option.role)}
            className={rowClass}
          >
            {labelFor(option.role)}
            <span
              className={cn(
                "inline-flex min-w-0 items-center gap-[7px] font-mono text-[11px]",
                touched ? "text-body" : "text-ghost"
              )}
            >
              <span className="max-w-[118px] min-w-0 truncate">
                {selection?.model ?? selection?.effort ?? "Default"}
              </span>
              <ChevronRight className="size-3 shrink-0 opacity-50" aria-hidden="true" />
            </span>
          </button>
        )
      })}
    </>
  )
}

export { AgentsMenu, ROLE_LABELS }
