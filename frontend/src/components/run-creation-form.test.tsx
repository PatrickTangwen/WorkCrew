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

function chooseButtonIn(groupLabel: string) {
  const group = screen.getByRole("group", { name: groupLabel })
  return within(group).getByRole("button", { name: /^Choos/ })
}

async function selectPath(groupLabel: string, path: string) {
  vi.mocked(pickPath).mockResolvedValueOnce(path)
  fireEvent.click(chooseButtonIn(groupLabel))
  await screen.findByTitle(path)
}

function typeTask(text: string) {
  fireEvent.change(screen.getByLabelText("Task"), { target: { value: text } })
}

async function fillRequiredInputs() {
  await selectPath("Source folder input", "/home/operator/source")
  await selectPath("Workbook input", "/home/operator/template.xlsx")
  typeTask("One row per charity folder")
}

describe("RunCreationForm", () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.mocked(pickPath).mockReset()
    vi.mocked(createRun).mockReset()
    vi.mocked(createRun).mockResolvedValue(createdRun)
  })

  it("starts a run from two paths and a task, with no rules", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    const startButton = screen.getByRole("button", { name: "Start run" })

    expect(startButton).toBeDisabled()
    await fillRequiredInputs()

    expect(startButton).toBeEnabled()
    fireEvent.click(startButton)

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdRun))
    expect(createRun).toHaveBeenCalledWith({
      source: "/home/operator/source",
      workbook: "/home/operator/template.xlsx",
      task: "One row per charity folder",
      rules_text: null,
      rules_file: null,
      scoping_answers: null,
      review_policy: null,
    })
  })

  it("keeps the start button disabled until the task is described", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    await selectPath("Source folder input", "/home/operator/source")
    await selectPath("Workbook input", "/home/operator/template.xlsx")

    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled()
    typeTask("   ")
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled()
    typeTask("Fill the register")
    expect(screen.getByRole("button", { name: "Start run" })).toBeEnabled()
  })

  it("asks the chooser for the mode each path needs", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    await selectPath("Source folder input", "/home/operator/source")
    await selectPath("Workbook input", "/home/operator/template.xlsx")

    expect(vi.mocked(pickPath).mock.calls).toEqual([
      ["directory", "Choose source folder"],
      ["file", "Choose workbook"],
    ])
  })

  it("sends prose rules when the operator describes them", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()

    fireEvent.click(screen.getByRole("radio", { name: "Describe them" }))
    fireEvent.change(screen.getByLabelText("Rules"), {
      target: { value: "IDs are CHA- plus the registration number" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(createRun).toHaveBeenCalled())
    expect(vi.mocked(createRun).mock.calls[0][0]).toMatchObject({
      rules_text: "IDs are CHA- plus the registration number",
      rules_file: null,
    })
  })

  it("sends a rules file when the operator picks one", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()

    fireEvent.click(screen.getByRole("radio", { name: "Use a text file" }))
    await selectPath("Rules input", "/home/operator/rules.txt")
    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(createRun).toHaveBeenCalled())
    expect(vi.mocked(createRun).mock.calls[0][0]).toMatchObject({
      rules_text: null,
      rules_file: "/home/operator/rules.txt",
    })
  })

  it("does not expose scoping answers or review policy inputs", () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    expect(
      screen.queryByRole("group", { name: "Scoping answers input" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("group", { name: "Review policy input" })
    ).not.toBeInTheDocument()
  })

  it("blocks the run while a chosen rules mode is still empty", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()
    const startButton = screen.getByRole("button", { name: "Start run" })

    fireEvent.click(screen.getByRole("radio", { name: "Describe them" }))
    expect(startButton).toBeDisabled()

    fireEvent.click(screen.getByRole("radio", { name: "Use a text file" }))
    expect(startButton).toBeDisabled()

    fireEvent.click(screen.getByRole("radio", { name: "No rules" }))
    expect(startButton).toBeEnabled()
  })

  it("keeps the current value when the operator cancels the chooser", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await selectPath("Source folder input", "/home/operator/source")

    vi.mocked(pickPath).mockResolvedValueOnce(null)
    fireEvent.click(chooseButtonIn("Source folder input"))

    await waitFor(() =>
      expect(chooseButtonIn("Source folder input")).toBeEnabled()
    )
    expect(screen.getByTitle("/home/operator/source")).toBeVisible()
  })

  it("reports a chooser that cannot open", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    vi.mocked(pickPath).mockRejectedValueOnce(new Error("no display available"))
    fireEvent.click(chooseButtonIn("Source folder input"))

    expect(await screen.findByText("no display available")).toBeVisible()
  })
})
