import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RunCreationForm } from "@/components/run-creation-form"
import { createRun, pickPath, type RunRecord } from "@/lib/api"

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...original,
    pickPath: vi.fn(),
    createRun: vi.fn(),
  }
})

const createdRun: RunRecord = {
  run_id: "20260809-120000-abc123",
  status: "running",
  start_time: "2026-08-09T12:00:00Z",
  workspace_path: "/runs/20260809-120000-abc123",
  phase: "INITIALIZING",
  source_name: "source",
  workbook_name: "template.xlsx",
}

function chooseButtonFor(fieldLabel: string) {
  const inputGroup = screen.getByRole("group", { name: `${fieldLabel} input` })
  return within(inputGroup).getByRole("button", { name: /^Choos/ })
}

async function selectInput(fieldLabel: string, path: string) {
  vi.mocked(pickPath).mockResolvedValueOnce(path)
  fireEvent.click(chooseButtonFor(fieldLabel))
  await screen.findByTitle(path)
}

describe("RunCreationForm", () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.mocked(createRun).mockResolvedValue(createdRun)
    vi.mocked(pickPath).mockReset()
  })

  it("requires every engine input before creating a run", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    const startButton = screen.getByRole("button", { name: "Start run" })

    expect(startButton).toBeDisabled()
    await selectInput("Source folder", "/home/operator/source")
    await selectInput("Workbook", "/home/operator/template.xlsx")
    await selectInput("Rules folder", "/home/operator/rules")
    await selectInput("Workbook schema", "/home/operator/workbook-schema.json")

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

  it("asks the chooser for the mode each input needs", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    await selectInput("Source folder", "/home/operator/source")
    await selectInput("Workbook", "/home/operator/template.xlsx")

    expect(vi.mocked(pickPath).mock.calls).toEqual([
      ["directory", "Choose source folder"],
      ["file", "Choose workbook"],
    ])
  })

  it("keeps the current value when the operator cancels the chooser", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await selectInput("Source folder", "/home/operator/source")

    vi.mocked(pickPath).mockResolvedValueOnce(null)
    fireEvent.click(chooseButtonFor("Source folder"))

    await waitFor(() => expect(chooseButtonFor("Source folder")).toBeEnabled())
    expect(screen.getByTitle("/home/operator/source")).toBeVisible()
  })

  it("reports a chooser that cannot open", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    vi.mocked(pickPath).mockRejectedValueOnce(new Error("no display available"))
    fireEvent.click(chooseButtonFor("Source folder"))

    expect(await screen.findByText("no display available")).toBeVisible()
  })
})
