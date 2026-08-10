import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RunCreationForm } from "@/components/run-creation-form"
import {
  browseFiles,
  createRun,
  type BrowseEntry,
  type RunRecord,
} from "@/lib/api"

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...original,
    browseFiles: vi.fn(),
    createRun: vi.fn(),
  }
})

const homeEntries: BrowseEntry[] = [
  { name: "source", type: "directory", size: 0, modified: "2026-08-09T12:00:00Z" },
  { name: "rules", type: "directory", size: 0, modified: "2026-08-09T12:00:00Z" },
  { name: "template.xlsx", type: "file", size: 10, modified: "2026-08-09T12:00:00Z" },
  { name: "workbook-schema.json", type: "file", size: 10, modified: "2026-08-09T12:00:00Z" },
]

const createdRun: RunRecord = {
  run_id: "20260809-120000-abc123",
  status: "running",
  start_time: "2026-08-09T12:00:00Z",
  workspace_path: "/runs/20260809-120000-abc123",
  phase: "INITIALIZING",
  source_name: "source",
  workbook_name: "template.xlsx",
}

async function selectInput(
  fieldLabel: string,
  entryName: string,
  mode: "file" | "directory"
) {
  const inputGroup = screen.getByRole("group", { name: `${fieldLabel} input` })
  fireEvent.click(within(inputGroup).getByRole("button", { name: "Choose" }))
  const dialog = await screen.findByRole("dialog")
  const escapedName = entryName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  fireEvent.click(
    within(dialog).getByRole("button", { name: new RegExp(`^${escapedName}`) })
  )
  if (mode === "directory") {
    const breadcrumbs = within(dialog).getByRole("navigation", {
      name: "Current path",
    })
    await waitFor(() =>
      expect(
        within(breadcrumbs).getByRole("button", {
          name: new RegExp(`^${escapedName}$`),
        })
      ).toBeVisible()
    )
  }
  fireEvent.click(
    within(dialog).getByRole("button", {
      name: mode === "directory" ? "Select folder" : "Select file",
    })
  )
}

describe("RunCreationForm", () => {
  beforeEach(() => {
    vi.mocked(browseFiles).mockImplementation(async (path) => ({
      path: path ?? "/home/operator",
      root: "/home/operator",
      entries: path ? [] : homeEntries,
    }))
    vi.mocked(createRun).mockResolvedValue(createdRun)
  })

  it("requires every engine input before creating a run", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    const startButton = screen.getByRole("button", { name: "Start run" })

    expect(startButton).toBeDisabled()
    await selectInput("Source folder", "source", "directory")
    await selectInput("Workbook", "template.xlsx", "file")
    await selectInput("Rules folder", "rules", "directory")
    await selectInput("Workbook schema", "workbook-schema.json", "file")

    expect(startButton).toBeEnabled()
    fireEvent.click(startButton)

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdRun))
    expect(createRun).toHaveBeenCalledWith({
      source: "/home/operator/source",
      workbook: "/home/operator/template.xlsx",
      rules: "/home/operator/rules",
      workbook_schema: "/home/operator/workbook-schema.json",
      scoping_answers: null,
      review_policy: null,
    })
  })
})
