import { useState, type FormEvent } from "react"
import { FileJson, FileSpreadsheet, FileText, Folder, Play } from "lucide-react"

import { FileBrowserModal } from "@/components/file-browser-modal"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { createRun, type CreateRunInput, type RunRecord } from "@/lib/api"

type FieldKey = keyof CreateRunInput

const fields: Array<{
  key: FieldKey
  label: string
  description: string
  mode: "directory" | "file"
  required: boolean
  icon: typeof Folder
}> = [
  {
    key: "source",
    label: "Source folder",
    description: "Documents the workflow will read",
    mode: "directory",
    required: true,
    icon: Folder,
  },
  {
    key: "workbook",
    label: "Workbook",
    description: "Excel template to fill",
    mode: "file",
    required: true,
    icon: FileSpreadsheet,
  },
  {
    key: "rules",
    label: "Rules folder",
    description: "Reference and extraction rules",
    mode: "directory",
    required: true,
    icon: Folder,
  },
  {
    key: "workbook_schema",
    label: "Workbook schema",
    description: "JSON contract for writable cells",
    mode: "file",
    required: true,
    icon: FileJson,
  },
  {
    key: "scoping_answers",
    label: "Scoping answers",
    description: "Optional pre-answered questions",
    mode: "file",
    required: false,
    icon: FileText,
  },
  {
    key: "review_policy",
    label: "Review policy",
    description: "Optional YAML policy override",
    mode: "file",
    required: false,
    icon: FileText,
  },
]

const initialValues: CreateRunInput = {
  source: "",
  workbook: "",
  rules: "",
  workbook_schema: "",
  scoping_answers: null,
  review_policy: null,
}

function RunCreationForm({ onCreated }: { onCreated: (run: RunRecord) => void }) {
  const [values, setValues] = useState(initialValues)
  const [activeField, setActiveField] = useState<(typeof fields)[number] | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ready = fields
    .filter((field) => field.required)
    .every((field) => Boolean(values[field.key]))

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!ready) return
    setSubmitting(true)
    setError(null)
    try {
      onCreated(await createRun(values))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to start the run")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="mx-auto w-full max-w-4xl">
        <div className="mb-6">
          <p className="text-xs font-semibold tracking-[0.18em] text-muted-foreground uppercase">
            New run
          </p>
          <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight">
            Assemble the working set.
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Choose local inputs from your home directory. WorkCrew copies them into an isolated run workspace before any agent begins.
          </p>
        </div>

        <form onSubmit={(event) => void handleSubmit(event)}>
          <Card className="bg-background shadow-lg shadow-black/4">
            <CardHeader className="border-b">
              <CardTitle>Run inputs</CardTitle>
              <CardDescription>Required inputs are marked. Original files stay untouched.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              {fields.map((field) => {
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
                          {!field.required && (
                            <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">Optional</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-muted-foreground">{field.description}</p>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center gap-2">
                      <div
                        title={value ?? undefined}
                        className="min-w-0 flex-1 truncate rounded-md border bg-background px-2.5 py-2 font-mono text-xs text-muted-foreground"
                      >
                        {value || "Nothing selected"}
                      </div>
                      <Button size="sm" variant="outline" onClick={() => setActiveField(field)}>
                        Choose
                      </Button>
                    </div>
                  </div>
                )
              })}
            </CardContent>
            <div className="flex flex-col gap-3 border-t bg-muted/20 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div aria-live="polite" className="text-sm">
                {error ? (
                  <p className="text-destructive">{error}</p>
                ) : (
                  <p className="text-muted-foreground">
                    {ready ? "Inputs ready. Start when you are." : "Select all four required inputs."}
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

      <FileBrowserModal
        open={activeField !== null}
        title={activeField ? `Choose ${activeField.label.toLowerCase()}` : "Choose input"}
        mode={activeField?.mode ?? "file"}
        onClose={() => setActiveField(null)}
        onSelect={(path) => {
          if (activeField) {
            setValues((current) => ({ ...current, [activeField.key]: path }))
          }
        }}
      />
    </>
  )
}

export { RunCreationForm }
