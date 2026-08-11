import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { ArrowUp, ChevronDown, X } from "lucide-react"

import { AgentsMenu } from "@/components/agent-settings"
import { TopBar } from "@/components/top-bar"
import {
  createRun,
  listAgentOptions,
  pickPath,
  readTaskImage,
  SUPPORTED_IMAGE_TYPES,
  type AgentOption,
  type AgentSelection,
  type CreateRunInput,
  type PickMode,
  type RulesMode,
  type RunRecord,
  type TaskImageUpload,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type PathKey = "source" | "workbook"

/** A pasted image: what the operator sees, and what the API takes. */
type TaskImage = { preview: string; upload: TaskImageUpload }

const paths: Array<{
  key: PathKey
  label: string
  kind: string
  mode: PickMode
}> = [
  { key: "source", label: "Source folder", kind: "DIR", mode: "directory" },
  { key: "workbook", label: "Workbook", kind: "XLSX", mode: "file" },
]

const rulesModes: Array<{ mode: RulesMode; label: string }> = [
  { mode: "none", label: "No rules" },
  { mode: "text", label: "Describe them" },
  { mode: "file", label: "Use a text file" },
]

const starters = [
  {
    title: "One row per folder",
    description: "Key each source folder to a row and fill across.",
    task: "Fill one row per charity folder from the annual reports, keyed by registration number.",
  },
  {
    title: "Reconcile two sources",
    description: "Cross-check figures and flag every disagreement.",
    task: "Fill the workbook from the filings, and flag any cell where the filing and the summary sheet disagree.",
  },
  {
    title: "Extract a schedule",
    description: "Pull dated line items into the detail sheet.",
    task: "Extract every dated line item from the contracts into the Detail sheet, one row per item, newest first.",
  },
  {
    title: "Summarize per document",
    description: "One paragraph and key totals per source file.",
    task: "For each source document, write a one-paragraph summary and its key totals into the Summary sheet.",
  },
]

const chipClass =
  "inline-flex h-[30px] min-w-0 items-center gap-1.5 rounded-full border px-2.5 text-[11.5px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-default"

const menuClass =
  "absolute bottom-[38px] z-30 flex flex-col gap-0.5 rounded-xl border border-line-strong bg-surface p-[5px] shadow-[0_8px_22px_rgba(31,30,28,.14)]"

function basename(path: string) {
  return path.split("/").filter(Boolean).pop() ?? path
}

function RunCreationForm({ onCreated }: { onCreated: (run: RunRecord) => void }) {
  const [values, setValues] = useState<Record<PathKey, string>>({
    source: "",
    workbook: "",
  })
  const [task, setTask] = useState("")
  const [name, setName] = useState("")
  const [rulesMode, setRulesMode] = useState<RulesMode>("none")
  const [rulesText, setRulesText] = useState("")
  const [rulesFile, setRulesFile] = useState("")
  const [pickingKey, setPickingKey] = useState<PathKey | "rules" | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentOptions, setAgentOptions] = useState<AgentOption[]>([])
  const [agentOptionsStatus, setAgentOptionsStatus] = useState<
    "loading" | "ready" | "error"
  >("loading")
  const [agentOptionsError, setAgentOptionsError] = useState<string | null>(null)
  const [agents, setAgents] = useState<Record<string, AgentSelection>>({})
  const [openMenu, setOpenMenu] = useState<"rules" | "agents" | null>(null)
  const [openRole, setOpenRole] = useState<string | null>(null)
  const [images, setImages] = useState<TaskImage[]>([])
  const agentOptionsRequestRef = useRef(0)

  // Object URLs back the thumbnails. Removing one image revokes its own
  // URL; the rest are revoked when the form goes away. Keying this on
  // `images` would revoke the URLs of thumbnails still on screen.
  const imagesRef = useRef(images)
  imagesRef.current = images
  useEffect(
    () => () => {
      for (const image of imagesRef.current) URL.revokeObjectURL(image.preview)
    },
    []
  )

  // Any click that is not on a chip or inside its panel dismisses both menus.
  useEffect(() => {
    if (openMenu === null) return
    function dismiss() {
      setOpenMenu(null)
      setOpenRole(null)
    }
    document.addEventListener("click", dismiss)
    return () => document.removeEventListener("click", dismiss)
  }, [openMenu])

  async function addPastedImages(files: File[]) {
    const supported = files.filter((file) =>
      SUPPORTED_IMAGE_TYPES.includes(file.type)
    )
    if (supported.length === 0) return
    setError(null)
    const added = await Promise.all(
      supported.map(async (file) => ({
        preview: URL.createObjectURL(file),
        upload: await readTaskImage(file),
      }))
    )
    setImages((current) => [...current, ...added])
  }

  function removeImage(index: number) {
    setImages((current) => {
      URL.revokeObjectURL(current[index].preview)
      return current.filter((_, position) => position !== index)
    })
  }

  const loadAgentSettings = useCallback(async () => {
    const request = ++agentOptionsRequestRef.current
    setAgentOptionsStatus("loading")
    setAgentOptionsError(null)
    try {
      const options = await listAgentOptions()
      if (request !== agentOptionsRequestRef.current) return
      setAgentOptions(options)
      setAgentOptionsStatus("ready")
    } catch (cause) {
      if (request !== agentOptionsRequestRef.current) return
      setAgentOptionsError(
        cause instanceof Error ? cause.message : "Unable to load agent settings"
      )
      setAgentOptionsStatus("error")
    }
  }, [])

  useEffect(() => {
    // The server owns the roles, defaults and effort vocabularies. Do not
    // silently run with defaults when that contract could not be loaded.
    void loadAgentSettings()
    return () => {
      agentOptionsRequestRef.current += 1
    }
  }, [loadAgentSettings])

  const chosenAgents = Object.fromEntries(
    Object.entries(agents).filter(
      ([, selection]) => selection.model !== null || selection.effort !== null
    )
  )

  const rulesReady =
    rulesMode === "text"
      ? rulesText.trim().length > 0
      : rulesMode === "file"
        ? Boolean(rulesFile)
        : true

  const ready =
    Boolean(values.source) &&
    Boolean(values.workbook) &&
    task.trim().length > 0 &&
    agentOptionsStatus === "ready" &&
    rulesReady

  const readyLine = ready
    ? "Inputs ready. Start when you are."
    : agentOptionsStatus === "loading"
      ? "Loading agent settings…"
      : agentOptionsStatus === "error"
        ? "Agent settings could not be loaded. Retry before starting."
        : !values.source || !values.workbook
          ? "Select the source folder and workbook, then describe the task."
          : task.trim().length === 0
            ? "Describe what this run should produce."
            : rulesMode === "text"
              ? "Write the rules, or switch back to No rules."
              : "Choose the rules file, or switch back to No rules."

  async function choose(key: PathKey | "rules", mode: PickMode, prompt: string) {
    setPickingKey(key)
    setError(null)
    try {
      const picked = await pickPath(mode, prompt)
      if (picked === null) return
      if (key === "rules") setRulesFile(picked)
      else setValues((current) => ({ ...current, [key]: picked }))
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Unable to open the file chooser"
      )
    } finally {
      setPickingKey(null)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready) return
    setSubmitting(true)
    setError(null)
    const input: CreateRunInput = {
      source: values.source,
      workbook: values.workbook,
      task: task.trim(),
      name: name.trim() || null,
      // Only what the operator actually chose; the server resolves the
      // rest against its own pinned defaults.
      agents: Object.keys(chosenAgents).length > 0 ? chosenAgents : null,
      task_images: images.map((image) => image.upload),
      rules_text: rulesMode === "text" ? rulesText.trim() : null,
      rules_file: rulesMode === "file" ? rulesFile : null,
      scoping_answers: null,
      review_policy: null,
    }
    try {
      onCreated(await createRun(input))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start the run")
    } finally {
      setSubmitting(false)
    }
  }

  function toggleMenu(menu: "rules" | "agents") {
    setOpenMenu((current) => (current === menu ? null : menu))
    setOpenRole(null)
  }

  const agentsChanged = Object.keys(chosenAgents).length
  const rulesChosen = rulesMode !== "none"

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-1 flex-col">
      <TopBar
        title={
          <input
            aria-label="Run name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Name this run (optional)"
            className="min-w-0 max-w-[320px] flex-1 bg-transparent text-sm font-medium text-ink outline-none placeholder:text-faint"
          />
        }
      />

      <div className="mx-auto flex w-full max-w-[680px] flex-1 flex-col justify-center px-8 pt-5 pb-8">
        <div className="text-center">
          <h1 className="text-[26px] leading-[1.25] font-semibold tracking-[-0.025em] text-ink">
            What should this run produce?
          </h1>
          <p className="mt-2 text-[13px] text-faint">
            Describe it in plain language — scoping derives the workbook schema itself.
          </p>
        </div>

        <div className="mt-5 rounded-[18px] border border-line-strong bg-surface shadow-[0_1px_3px_rgba(31,30,28,.05)]">
          <textarea
            aria-label="Task"
            value={task}
            onChange={(event) => setTask(event.target.value)}
            onPaste={(event) => {
              const files = Array.from(event.clipboardData.files)
              if (files.length === 0) return
              // Keep the pasted image out of the text box itself.
              event.preventDefault()
              void addPastedImages(files)
            }}
            rows={3}
            placeholder="e.g. Fill one row per charity folder from the annual reports, keyed by registration number."
            className="block w-full resize-none bg-transparent px-[18px] pt-[17px] pb-1 text-sm leading-[1.65] text-ink outline-none placeholder:text-faint"
          />

          {images.length > 0 ? (
            <ul
              aria-label="Task images"
              className="flex flex-wrap gap-2.5 px-[18px] pt-2 pb-0.5"
            >
              {images.map((image, index) => (
                <li key={image.preview} className="relative inline-flex">
                  <img
                    src={image.preview}
                    alt={`Task image ${index + 1}`}
                    className="size-[62px] rounded-[9px] border border-line-strong object-cover"
                  />
                  <button
                    type="button"
                    aria-label={`Remove task image ${index + 1}`}
                    onClick={() => removeImage(index)}
                    className="absolute -top-1.5 -right-1.5 grid size-[18px] cursor-pointer place-items-center rounded-full border border-line-strong bg-surface text-subtle shadow-sm hover:bg-shell"
                  >
                    <X className="size-2.5" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-[18px] pt-0.5 text-[11px] text-ghost">
              Paste screenshots into the task — the agents read them with your words.
            </p>
          )}

          {rulesMode === "text" && (
            <div className="mx-3.5 mt-0.5 border-t border-line-soft pt-2.5">
              <span className="block font-mono text-[9px] font-semibold tracking-[0.16em] text-ghost uppercase">
                Rules
              </span>
              <textarea
                aria-label="Rules"
                value={rulesText}
                onChange={(event) => setRulesText(event.target.value)}
                rows={3}
                placeholder="e.g. Charity IDs are CHA- followed by the registration number. Income under 100k is Small, under 1m Medium, otherwise Large."
                className="mt-1 block w-full resize-none bg-transparent text-[12.5px] leading-[1.6] text-body outline-none placeholder:text-ghost"
              />
            </div>
          )}

          {rulesMode === "file" && (
            <div className="mx-3.5 mt-0.5 flex items-center gap-2 border-t border-line-soft pt-2.5">
              <span
                title={rulesFile || undefined}
                className={cn(
                  "min-w-0 flex-1 truncate font-mono text-[11px]",
                  rulesFile ? "text-body" : "text-ghost"
                )}
              >
                {rulesFile || "Nothing selected"}
              </span>
              <button
                type="button"
                aria-label={rulesFile ? "Change rules file" : "Choose rules file"}
                disabled={pickingKey !== null}
                onClick={() => void choose("rules", "file", "Choose rules file")}
                className="h-7 shrink-0 cursor-pointer rounded-lg border border-line-strong bg-paper px-2.5 text-[11px] font-medium text-ink transition-colors hover:bg-shell disabled:cursor-default disabled:text-ghost"
              >
                {pickingKey === "rules"
                  ? "Choosing…"
                  : rulesFile
                    ? "Change"
                    : "Choose"}
              </button>
            </div>
          )}

          <div className="flex items-center gap-1.5 py-3 pr-3 pl-3.5">
            {paths.map((field) => {
              const value = values[field.key]
              const busy = pickingKey === field.key
              return (
                <button
                  key={field.key}
                  type="button"
                  title={value || undefined}
                  aria-label={`${field.label}: ${value || "nothing selected"}`}
                  disabled={pickingKey !== null}
                  onClick={() =>
                    void choose(
                      field.key,
                      field.mode,
                      `Choose ${field.label.toLowerCase()}`
                    )
                  }
                  className={cn(
                    chipClass,
                    "cursor-pointer",
                    value
                      ? "border-solid border-line-strong bg-shell"
                      : "border-dashed border-brand/45 bg-brand/7"
                  )}
                >
                  <span
                    className={cn(
                      "shrink-0 font-mono text-[8.5px] font-medium tracking-[0.08em]",
                      value ? "text-subtle" : "text-brand"
                    )}
                  >
                    {field.kind}
                  </span>
                  <span className="max-w-[126px] min-w-0 truncate text-ink">
                    {busy ? "Choosing…" : value ? basename(value) : field.label}
                  </span>
                  {!value && !busy && (
                    <span className="shrink-0 font-mono text-[8.5px] font-semibold tracking-[0.12em] text-brand uppercase">
                      Required
                    </span>
                  )}
                </button>
              )
            })}

            <span className="relative inline-flex">
              <button
                type="button"
                aria-haspopup="true"
                aria-expanded={openMenu === "rules"}
                onClick={(event) => {
                  event.stopPropagation()
                  toggleMenu("rules")
                }}
                className={cn(
                  chipClass,
                  "cursor-pointer",
                  rulesChosen
                    ? "border-solid border-line-strong bg-shell text-ink"
                    : "border-dashed border-line-dash bg-transparent text-subtle"
                )}
              >
                {rulesMode === "text"
                  ? "Rules · described"
                  : rulesMode === "file"
                    ? "Rules · file"
                    : "Rules"}
                <ChevronDown className="size-2.5 opacity-55" aria-hidden="true" />
              </button>
              {openMenu === "rules" && (
                <div
                  role="radiogroup"
                  aria-label="Rules source"
                  onClick={(event) => event.stopPropagation()}
                  className={cn(menuClass, "left-0 min-w-[168px]")}
                >
                  {rulesModes.map((option) => {
                    const chosen = rulesMode === option.mode
                    return (
                      <button
                        key={option.mode}
                        type="button"
                        role="radio"
                        aria-checked={chosen}
                        onClick={() => {
                          setRulesMode(option.mode)
                          setOpenMenu(null)
                        }}
                        className={cn(
                          "flex h-[30px] cursor-pointer items-center justify-between gap-2.5 rounded-lg px-2.5 text-left text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                          chosen ? "bg-line-soft text-ink" : "text-body hover:bg-line-soft/60"
                        )}
                      >
                        {option.label}
                        <span
                          aria-hidden="true"
                          className={cn("font-mono text-[11px]", !chosen && "opacity-0")}
                        >
                          ✓
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </span>

            <span className="relative inline-flex">
              <button
                type="button"
                aria-haspopup="true"
                aria-expanded={openMenu === "agents"}
                onClick={(event) => {
                  event.stopPropagation()
                  toggleMenu("agents")
                }}
                className={cn(
                  chipClass,
                  "cursor-pointer whitespace-nowrap",
                  agentOptionsStatus === "error"
                    ? "border-solid border-bad-line bg-bad-wash text-bad"
                    : agentsChanged > 0
                      ? "border-solid border-line-strong bg-shell text-ink"
                      : "border-dashed border-line-dash bg-transparent text-subtle"
                )}
              >
                {agentOptionsStatus === "loading"
                  ? "Agents · loading…"
                  : agentOptionsStatus === "error"
                    ? "Agents · unavailable"
                    : "Agents"}
                <ChevronDown className="size-2.5 opacity-55" aria-hidden="true" />
              </button>
              {openMenu === "agents" && (
                <div
                  onClick={(event) => event.stopPropagation()}
                  className={cn(menuClass, "right-0 min-w-[250px]")}
                >
                  {agentOptionsStatus === "ready" && (
                    <AgentsMenu
                      options={agentOptions}
                      selections={agents}
                      openRole={openRole}
                      onOpenRole={setOpenRole}
                      onChange={(role, selection) =>
                        setAgents((current) => ({ ...current, [role]: selection }))
                      }
                    />
                  )}
                  {agentOptionsStatus === "loading" && (
                    <p role="status" className="px-2.5 py-2 text-xs text-faint">
                      Loading agent settings…
                    </p>
                  )}
                  {agentOptionsStatus === "error" && (
                    <div className="flex flex-col gap-2 px-2 py-[7px]">
                      <p role="alert" className="text-[11.5px] leading-[1.5] text-bad">
                        {agentOptionsError}
                      </p>
                      <button
                        type="button"
                        onClick={() => void loadAgentSettings()}
                        className="h-[27px] cursor-pointer rounded-[7px] border border-bad-line bg-bad-wash px-2.5 text-[11px] font-medium text-bad transition-colors hover:bg-bad-surface"
                      >
                        Retry agent settings
                      </button>
                    </div>
                  )}
                </div>
              )}
            </span>

            <span className="flex-1" />

            <button
              type="submit"
              aria-label="Start run"
              title={readyLine}
              disabled={!ready || submitting}
              className={cn(
                "grid size-8 shrink-0 place-items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                ready && !submitting
                  ? "cursor-pointer bg-brand text-white hover:bg-brand/90"
                  : "cursor-default bg-raise text-ghost"
              )}
            >
              <ArrowUp className="size-[15px]" strokeWidth={1.8} aria-hidden="true" />
            </button>
          </div>
        </div>

        <p
          aria-live="polite"
          className={cn(
            "mt-3 text-center text-[11.5px]",
            error ? "text-bad" : "text-faint"
          )}
        >
          {error ?? (submitting ? "Starting…" : readyLine)}
        </p>

        <div className="mt-6 grid grid-cols-2 gap-2">
          {starters.map((starter) => (
            <button
              key={starter.title}
              type="button"
              onClick={() => setTask(starter.task)}
              className="min-w-0 cursor-pointer rounded-xl border border-line bg-surface px-3.5 py-3 text-left transition-colors hover:bg-shell focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <span className="block truncate text-[13px] font-medium text-ink">
                {starter.title}
              </span>
              <span className="mt-[3px] block text-xs leading-[1.45] text-pretty text-faint">
                {starter.description}
              </span>
            </button>
          ))}
        </div>
      </div>
    </form>
  )
}

export { RunCreationForm }
