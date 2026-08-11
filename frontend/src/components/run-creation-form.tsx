import { useCallback, useEffect, useRef, useState, type FormEvent } from "react"
import { FileSpreadsheet, Folder, Play, X } from "lucide-react"

import { AgentSettings } from "@/components/agent-settings"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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
  description: string
  mode: PickMode
  icon: typeof Folder
}> = [
  {
    key: "source",
    label: "Source folder",
    description: "Documents the workflow will read",
    mode: "directory",
    icon: Folder,
  },
  {
    key: "workbook",
    label: "Workbook",
    description: "Excel template to fill",
    mode: "file",
    icon: FileSpreadsheet,
  },
]

const rulesModes: Array<{ mode: RulesMode; label: string }> = [
  { mode: "none", label: "No rules" },
  { mode: "text", label: "Describe them" },
  { mode: "file", label: "Use a text file" },
]

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

  const ready =
    Boolean(values.source) &&
    Boolean(values.workbook) &&
    task.trim().length > 0 &&
    agentOptionsStatus === "ready" &&
    (rulesMode !== "text" || rulesText.trim().length > 0) &&
    (rulesMode !== "file" || Boolean(rulesFile))

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

  return (
    <div className="mx-auto w-full max-w-4xl">
      <div className="mb-6">
        <p className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">
          New run
        </p>
        <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight">
          Assemble the working set.
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
          Point WorkCrew at your documents and workbook, then say what you want done.
          The scoping pass reads the workbook and derives the field schema itself.
        </p>
      </div>

      <form onSubmit={(event) => void handleSubmit(event)}>
        <Card className="bg-background shadow-lg shadow-black/4">
          <CardHeader className="border-b">
            <CardTitle>Run inputs</CardTitle>
            <CardDescription>
              Your files are never modified. Results are written to a
              workcrew-output folder inside the source folder.
            </CardDescription>
          </CardHeader>

          <CardContent className="grid gap-3 sm:grid-cols-2">
            {paths.map((field) => {
              const Icon = field.icon
              const value = values[field.key]
              return (
                <div
                  key={field.key}
                  role="group"
                  aria-label={`${field.label} input`}
                  className="rounded-xl border bg-muted/18 p-3"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid size-9 shrink-0 place-items-center rounded-lg border bg-background">
                      <Icon className="size-4" aria-hidden="true" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{field.label}</p>
                        <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                          Required
                        </span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {field.description}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div
                      title={value || undefined}
                      className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                    >
                      {value || "Nothing selected"}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      type="button"
                      disabled={pickingKey !== null}
                      onClick={() =>
                        void choose(
                          field.key,
                          field.mode,
                          `Choose ${field.label.toLowerCase()}`
                        )
                      }
                    >
                      {pickingKey === field.key ? "Choosing…" : "Choose"}
                    </Button>
                  </div>
                </div>
              )
            })}
          </CardContent>

          <CardContent>
            <div
              role="group"
              aria-label="Run name input"
              className="rounded-xl border bg-muted/18 p-3"
            >
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Run name</p>
                <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  Optional
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Names the run, so its id reads as more than a timestamp.
              </p>
              <input
                aria-label="Run name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. charity 2015 review"
                className="mt-3 w-full rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
              <p className="mt-2 text-xs text-muted-foreground">
                Without a name, the source folder names the run.
              </p>
            </div>
          </CardContent>

          <CardContent>
            <div
              role="group"
              aria-label="Task input"
              className="rounded-xl border bg-muted/18 p-3"
            >
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">Task</p>
                <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                  Required
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                What should this run produce? The workbook schema is derived from
                this. Paste screenshots straight into the box — the agents read
                them with your words.
              </p>
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
                rows={4}
                placeholder="e.g. Fill one row per charity folder from the annual reports, keyed by registration number."
                className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />

              {images.length > 0 && (
                <ul
                  aria-label="Task images"
                  className="mt-3 flex flex-wrap gap-2"
                >
                  {images.map((image, index) => (
                    <li key={image.preview} className="relative">
                      <img
                        src={image.preview}
                        alt={`Task image ${index + 1}`}
                        className="size-20 rounded-lg border object-cover"
                      />
                      <button
                        type="button"
                        aria-label={`Remove task image ${index + 1}`}
                        onClick={() => removeImage(index)}
                        className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border bg-background text-xs shadow-sm hover:bg-muted"
                      >
                        <X className="size-3" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>

          <CardContent>
            <div
              role="group"
              aria-label="Rules input"
              className="rounded-xl border bg-muted/18 p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">Rules</p>
                    <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                      Optional
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Extraction conventions the agents should follow
                  </p>
                </div>
                <div role="radiogroup" aria-label="Rules source" className="flex gap-1">
                  {rulesModes.map((option) => (
                    <button
                      key={option.mode}
                      type="button"
                      role="radio"
                      aria-checked={rulesMode === option.mode}
                      onClick={() => setRulesMode(option.mode)}
                      className={cn(
                        "rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                        rulesMode === option.mode
                          ? "border-foreground/25 bg-foreground text-background"
                          : "bg-background hover:bg-muted"
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              {rulesMode === "text" && (
                <textarea
                  aria-label="Rules"
                  value={rulesText}
                  onChange={(event) => setRulesText(event.target.value)}
                  rows={4}
                  placeholder="e.g. Charity IDs are CHA- followed by the registration number. Income under 100k is Small, under 1m Medium, otherwise Large."
                  className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                />
              )}

              {rulesMode === "file" && (
                <div className="mt-3 flex items-center gap-2">
                  <div
                    title={rulesFile || undefined}
                    className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                  >
                    {rulesFile || "Nothing selected"}
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    type="button"
                    disabled={pickingKey !== null}
                    onClick={() => void choose("rules", "file", "Choose rules file")}
                  >
                    {pickingKey === "rules" ? "Choosing…" : "Choose"}
                  </Button>
                </div>
              )}
            </div>
          </CardContent>

          <CardContent>
            {agentOptionsStatus === "ready" ? (
              <AgentSettings
                options={agentOptions}
                selections={agents}
                onChange={(role, selection) =>
                  setAgents((current) => ({ ...current, [role]: selection }))
                }
              />
            ) : agentOptionsStatus === "loading" ? (
              <p className="text-sm text-muted-foreground" role="status">
                Loading agent settings…
              </p>
            ) : (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-3">
                <p className="text-sm text-destructive" role="alert">
                  {agentOptionsError}
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => void loadAgentSettings()}
                >
                  Retry agent settings
                </Button>
              </div>
            )}
          </CardContent>

          <div className="flex flex-col gap-3 border-t bg-muted/20 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
            <div aria-live="polite" className="text-sm">
              {error ? (
                <p className="text-destructive">{error}</p>
              ) : (
                <p className="text-muted-foreground">
                  {ready
                    ? "Inputs ready. Start when you are."
                    : "Select the source folder and workbook, then describe the task."}
                </p>
              )}
            </div>
            <Button type="submit" disabled={!ready || submitting} className="min-w-32">
              <Play /> {submitting ? "Starting…" : "Start run"}
            </Button>
          </div>
        </Card>
      </form>
    </div>
  )
}

export { RunCreationForm }
