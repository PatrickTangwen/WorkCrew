import type { AgentOption, AgentSelection } from "@/lib/api"

const ROLE_LABELS: Record<string, string> = {
  scoping: "Scoping",
  filler: "Filler",
  revision: "Revision",
  reviewer: "Review",
  re_review: "Re-review",
}

type AgentSettingsProps = {
  options: AgentOption[]
  selections: Record<string, AgentSelection>
  onChange: (role: string, selection: AgentSelection) => void
}

/** Per-role model and reasoning effort, collapsed until asked for. */
function AgentSettings({ options, selections, onChange }: AgentSettingsProps) {
  if (options.length === 0) return null

  const changed = options.filter((option) => {
    const selection = selections[option.role]
    return Boolean(selection?.model) || Boolean(selection?.effort)
  }).length

  return (
    <details className="rounded-xl border bg-muted/18 p-3">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        Agents
        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
          Optional
        </span>
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {changed === 0 ? "Defaults" : `${changed} changed`}
        </span>
      </summary>

      <p className="mt-2 text-xs text-muted-foreground">
        Model and reasoning effort per role. Leave a field alone to keep the
        pinned default.
      </p>

      <div className="mt-3 grid gap-2">
        {options.map((option) => {
          const selection = selections[option.role] ?? { model: null, effort: null }
          const modelListId = `models-${option.role}`
          return (
            <div
              key={option.role}
              role="group"
              aria-label={`${ROLE_LABELS[option.role] ?? option.role} agent`}
              className="grid gap-2 rounded-lg border bg-background p-2.5 sm:grid-cols-[8rem_minmax(0,1fr)_9rem] sm:items-center"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {ROLE_LABELS[option.role] ?? option.role}
                </p>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {option.runtime}
                </p>
              </div>

              <input
                aria-label={`${ROLE_LABELS[option.role] ?? option.role} model`}
                list={modelListId}
                value={selection.model ?? ""}
                placeholder={option.model}
                onChange={(event) =>
                  onChange(option.role, {
                    ...selection,
                    model: event.target.value.trim() || null,
                  })
                }
                className="min-w-0 rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
              <datalist id={modelListId}>
                {option.model_suggestions.map((model) => (
                  <option key={model} value={model} />
                ))}
              </datalist>

              <select
                aria-label={`${ROLE_LABELS[option.role] ?? option.role} effort`}
                value={selection.effort ?? ""}
                onChange={(event) =>
                  onChange(option.role, {
                    ...selection,
                    effort: event.target.value || null,
                  })
                }
                className="rounded-md border bg-background px-2 py-1.5 text-xs outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              >
                <option value="">
                  {option.effort ? `Default (${option.effort})` : "Default"}
                </option>
                {option.effort_choices.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </div>
          )
        })}
      </div>
    </details>
  )
}

export { AgentSettings, ROLE_LABELS }
