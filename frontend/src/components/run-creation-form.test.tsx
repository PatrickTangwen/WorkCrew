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
import {
  createRun,
  listAgentOptions,
  pickPath,
  type AgentOption,
  type RunRecord,
} from "@/lib/api"

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...original,
    pickPath: vi.fn(),
    createRun: vi.fn(),
    listAgentOptions: vi.fn(),
  }
})

const agentOptions: AgentOption[] = [
  {
    role: "filler",
    runtime: "claude",
    model: "claude-opus-4-6[1m]",
    model_suggestions: ["claude-opus-4-6[1m]", "claude-sonnet-5"],
    effort: null,
    effort_choices: ["low", "medium", "high", "xhigh", "max"],
  },
  {
    role: "reviewer",
    runtime: "codex",
    model: "gpt-5.6-sol",
    model_suggestions: ["gpt-5.6-sol"],
    effort: "high",
    effort_choices: ["low", "medium", "high", "max", "ultra"],
  },
]

const createdRun: RunRecord = {
  run_id: "20260809-120000-abc123",
  status: "running",
  start_time: "2026-08-09T12:00:00Z",
  finished_at: null,
  workspace_path: "/runs/20260809-120000-abc123",
  phase: "INITIALIZING",
  source_name: "source",
  workbook_name: "template.xlsx",
}

function pasteImage(name: string, type = "image/png") {
  const file = new File([new Uint8Array([1, 2, 3, 4])], name, { type })
  fireEvent.paste(screen.getByLabelText("Task"), {
    clipboardData: { files: [file], getData: () => "" },
  })
}

/** The composer states each chosen path on its own chip. */
function pathChip(label: string) {
  return screen.getByRole("button", { name: new RegExp(`^${label}: `) })
}

async function selectPath(label: string, path: string) {
  vi.mocked(pickPath).mockResolvedValueOnce(path)
  fireEvent.click(pathChip(label))
  await screen.findByTitle(path)
}

async function selectRulesFile(path: string) {
  vi.mocked(pickPath).mockResolvedValueOnce(path)
  fireEvent.click(screen.getByRole("button", { name: "Choose rules file" }))
  await screen.findByTitle(path)
}

/** Rules and agents each live behind a chip that opens a menu. */
function chooseRulesMode(label: string) {
  fireEvent.click(screen.getByRole("button", { name: /^Rules/ }))
  fireEvent.click(screen.getByRole("radio", { name: label }))
}

async function openAgentsMenu() {
  fireEvent.click(await screen.findByRole("button", { name: "Agents" }))
}

async function openAgent(label: string) {
  await openAgentsMenu()
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${label}`) }))
}

function typeTask(text: string) {
  fireEvent.change(screen.getByLabelText("Task"), { target: { value: text } })
}

async function fillRequiredInputs() {
  await selectPath("Source folder", "/home/operator/source")
  await selectPath("Workbook", "/home/operator/template.xlsx")
  typeTask("One row per charity folder")
}

describe("RunCreationForm", () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.mocked(pickPath).mockReset()
    vi.mocked(createRun).mockReset()
    vi.mocked(createRun).mockResolvedValue(createdRun)
    vi.mocked(listAgentOptions).mockReset()
    vi.mocked(listAgentOptions).mockResolvedValue(agentOptions)
  })

  it("sends only the agent choices the operator changed", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    await fillRequiredInputs()
    // The menu lists the roles once the server has described them.
    await openAgent("Review")

    fireEvent.click(
      within(screen.getByRole("radiogroup", { name: "Review effort" })).getByRole(
        "radio",
        { name: "max" }
      )
    )
    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdRun))
    // Filler was left alone, so it is not in the request at all.
    expect(vi.mocked(createRun).mock.calls[0][0].agents).toEqual({
      reviewer: { model: null, effort: "max" },
    })
  })

  it("keeps the defaults out of the request when nothing is chosen", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()
    await openAgent("Review")

    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(createRun).toHaveBeenCalled())
    expect(vi.mocked(createRun).mock.calls[0][0].agents).toBeNull()
  })

  it("blocks the run and offers retry when agent options cannot load", async () => {
    vi.mocked(listAgentOptions)
      .mockRejectedValueOnce(new Error("agent options unavailable"))
      .mockResolvedValueOnce(agentOptions)
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()

    fireEvent.click(
      await screen.findByRole("button", { name: "Agents · unavailable" })
    )
    expect(screen.getByText("agent options unavailable")).toBeVisible()
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled()

    // The menu stays open across the retry, so the roles replace the error.
    fireEvent.click(screen.getByRole("button", { name: "Retry agent settings" }))

    fireEvent.click(await screen.findByRole("button", { name: /^Review/ }))
    expect(
      screen.getByRole("radiogroup", { name: "Review effort" })
    ).toBeVisible()
    expect(screen.getByRole("button", { name: "Start run" })).toBeEnabled()
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
      name: null,
      agents: null,
      task_images: [],
      rules_text: null,
      rules_file: null,
      scoping_answers: null,
      review_policy: null,
    })
  })

  it("sends the run name without predicting the server-owned id", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    await fillRequiredInputs()

    fireEvent.change(screen.getByLabelText("Run name"), {
      target: { value: "Charity 2015 review" },
    })
    expect(screen.queryByText(/charity-2015-review/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdRun))
    expect(vi.mocked(createRun).mock.calls[0][0].name).toBe("Charity 2015 review")
  })

  it("leaves the run id to the server when no name is given", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await selectPath("Source folder", "/home/operator/Charity Reports")

    expect(screen.getByLabelText("Run name")).toHaveAttribute(
      "placeholder",
      "Name this run (optional)"
    )
    expect(screen.queryByText(/charity-reports/)).not.toBeInTheDocument()
  })

  it("carries images pasted into the task box, and lets them be removed", async () => {
    const onCreated = vi.fn()
    render(<RunCreationForm onCreated={onCreated} />)
    await fillRequiredInputs()

    pasteImage("shot-1.png")
    pasteImage("shot-2.png")
    // Reading the clipboard file is async, so the thumbnails arrive late.
    const gallery = await screen.findByRole("list", { name: "Task images" })
    await waitFor(() =>
      expect(within(gallery).getAllByRole("img")).toHaveLength(2)
    )

    fireEvent.click(screen.getByRole("button", { name: "Remove task image 1" }))
    fireEvent.click(screen.getByRole("button", { name: "Start run" }))

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(createdRun))
    const sent = vi.mocked(createRun).mock.calls[0][0].task_images
    expect(sent).toHaveLength(1)
    expect(sent[0].content_type).toBe("image/png")
    expect(sent[0].data.length).toBeGreaterThan(0)
  })

  it("ignores a pasted file that is not a supported image", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()

    pasteImage("notes.txt", "text/plain")

    await waitFor(() =>
      expect(screen.queryByRole("list", { name: "Task images" })).toBeNull()
    )
  })

  it("keeps the start button disabled until the task is described", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    await selectPath("Source folder", "/home/operator/source")
    await selectPath("Workbook", "/home/operator/template.xlsx")

    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled()
    typeTask("   ")
    expect(screen.getByRole("button", { name: "Start run" })).toBeDisabled()
    typeTask("Fill the register")
    expect(screen.getByRole("button", { name: "Start run" })).toBeEnabled()
  })

  it("asks the chooser for the mode each path needs", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    await selectPath("Source folder", "/home/operator/source")
    await selectPath("Workbook", "/home/operator/template.xlsx")

    expect(vi.mocked(pickPath).mock.calls).toEqual([
      ["directory", "Choose source folder"],
      ["file", "Choose workbook"],
    ])
  })

  it("sends prose rules when the operator describes them", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await fillRequiredInputs()

    chooseRulesMode("Describe them")
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

    chooseRulesMode("Use a text file")
    await selectRulesFile("/home/operator/rules.txt")
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

    chooseRulesMode("Describe them")
    expect(startButton).toBeDisabled()

    chooseRulesMode("Use a text file")
    expect(startButton).toBeDisabled()

    chooseRulesMode("No rules")
    expect(startButton).toBeEnabled()
  })

  it("keeps the current value when the operator cancels the chooser", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)
    await selectPath("Source folder", "/home/operator/source")

    vi.mocked(pickPath).mockResolvedValueOnce(null)
    fireEvent.click(pathChip("Source folder"))

    await waitFor(() => expect(pathChip("Source folder")).toBeEnabled())
    expect(screen.getByTitle("/home/operator/source")).toBeVisible()
  })

  it("reports a chooser that cannot open", async () => {
    render(<RunCreationForm onCreated={vi.fn()} />)

    vi.mocked(pickPath).mockRejectedValueOnce(new Error("no display available"))
    fireEvent.click(pathChip("Source folder"))

    expect(await screen.findByText("no display available")).toBeVisible()
  })
})
