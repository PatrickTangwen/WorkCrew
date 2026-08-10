import { useState, type FormEvent } from "react"
import { FileSpreadsheet, Folder, Play } from "lucide-react"

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
  pickPath,
  type CreateRunInput,
  type PickMode,
  type RulesMode,
  type RunRecord,
} from "@/lib/api"
import { cn } from "@/lib/utils"

type PathKey = "source" | "workbook"

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
  const [values, setValues] = useState({ source: "", workbook: "" })
  const [task, setTask] = useState("")
  const [rulesMode, setRulesMode] = useState<RulesMode>("none")
  const [rulesText, setRulesText] = useState("")
  const [rulesFile, setRulesFile] = useState("")
  const [pickingKey, setPickingKey] = useState<PathKey | "rules" | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready =
    Boolean(values.source) &&
    Boolean(values.workbook) &&
    task.trim().length > 0 &&
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
      rules_text: rulesMode === "text" ? rulesText.trim() : null,
      rules_file: rulesMode === "file" ? rulesFile : null,
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
            <CardDescription>Original files stay untouched.</CardDescription>
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
                What should this run produce? The workbook schema is derived from this.
              </p>
              <textarea
                aria-label="Task"
                value={task}
                onChange={(event) => setTask(event.target.value)}
                rows={4}
                placeholder="e.g. Fill one row per charity folder from the annual reports, keyed by registration number."
                className="mt-3 w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
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
