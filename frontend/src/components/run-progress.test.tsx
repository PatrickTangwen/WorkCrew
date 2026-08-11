import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RunDetail } from "@/components/run-detail"
import type { RunRecord, ScopingQuestions, WorkflowEvent } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

class MockWebSocket {
  static instances: MockWebSocket[] = []

  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onopen: (() => void) | null = null
  close = vi.fn()
  readonly url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  receive(event: WorkflowEvent) {
    act(() => {
      this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>)
    })
  }
}

const run: RunRecord = {
  run_id: "run-streaming",
  status: "running",
  start_time: "2026-08-09T12:00:00Z",
  workspace_path: "/runs/run-streaming",
  phase: "INITIALIZING",
  source_name: "source",
  workbook_name: "template.xlsx",
}

function StoredRunDetail() {
  const currentRun = useAppStore((state) => state.currentRun)
  return currentRun ? <RunDetail run={currentRun} /> : null
}

function event(
  value: { type: WorkflowEvent["type"] } & Record<string, unknown>,
  timestamp = "2026-08-09T12:30:00Z"
): WorkflowEvent {
  return { ...value, timestamp } as WorkflowEvent
}

describe("run progress", () => {
  beforeEach(() => {
    useAppStore.getState().disconnectRunStream()
    useAppStore.setState(useAppStore.getInitialState())
    MockWebSocket.instances = []
    vi.stubGlobal("WebSocket", MockWebSocket)
    Element.prototype.scrollIntoView = vi.fn()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it("connects for the mounted run detail and disconnects on unmount", () => {
    const view = render(<RunDetail run={run} />)

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toMatch(
      /\/ws\/runs\/run-streaming$/
    )

    view.unmount()

    expect(MockWebSocket.instances[0].close).toHaveBeenCalledOnce()
  })

  it("advances the six-stage pipeline and shows timestamped, auto-scrolling logs", () => {
    render(<RunDetail run={run} />)
    const socket = MockWebSocket.instances[0]

    socket.receive(
      event({
        type: "phase_change",
        phase: "CLAUDE_FILL",
        status: "active",
      })
    )
    socket.receive(
      event({
        type: "progress",
        phase: "CLAUDE_FILL",
        message: "Starting Filler...",
      })
    )

    const pipeline = screen.getByRole("list", { name: "Workflow stages" })
    expect(within(pipeline).getByText("Scoping").closest("li")).toHaveAttribute(
      "data-status",
      "completed"
    )
    expect(within(pipeline).getByText("Filler").closest("li")).toHaveAttribute(
      "data-status",
      "active"
    )
    expect(within(pipeline).getByText("Review").closest("li")).toHaveAttribute(
      "data-status",
      "pending"
    )
    expect(screen.getByText("Starting Filler...")).toBeVisible()
    const progressEntry = screen.getByText("Starting Filler...").closest("li")
    expect(
      progressEntry?.querySelector('time[datetime="2026-08-09T12:30:00Z"]')
    ).not.toBeNull()
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()

    socket.receive(
      event({
        type: "phase_change",
        phase: "CODEX_REVIEW",
        status: "failed",
      })
    )
    socket.receive(event({ type: "failed", error: "Reviewer timed out" }))

    expect(within(pipeline).getByText("Review").closest("li")).toHaveAttribute(
      "data-status",
      "failed"
    )
    expect(screen.getAllByText("Reviewer timed out").length).toBeGreaterThan(0)
  })

  it("marks every stage completed when the run completes", () => {
    render(<RunDetail run={run} />)

    MockWebSocket.instances[0].receive(
      event({ type: "completed", final_xlsx: "/runs/run-streaming/output/final.xlsx" })
    )

    const stages = within(
      screen.getByRole("list", { name: "Workflow stages" })
    ).getAllByRole("listitem")
    expect(stages).toHaveLength(6)
    expect(stages.every((stage) => stage.dataset.status === "completed")).toBe(true)
  })

  it("offers Cancel only while running and updates detail state from the response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ...run, status: "cancelled" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    )
    act(() => useAppStore.getState().showRun(run))
    render(<StoredRunDetail />)

    expect(screen.getByRole("button", { name: "Cancel run" })).toBeVisible()
    expect(screen.queryByRole("button", { name: "Retry run" })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Cancel run" }))

    await waitFor(() =>
      expect(useAppStore.getState().currentRun?.status).toBe("cancelled")
    )
    expect(fetch).toHaveBeenCalledWith(
      "/api/runs/run-streaming/cancel",
      expect.objectContaining({ method: "POST" })
    )
    expect(useAppStore.getState().runs[0].status).toBe("cancelled")
    expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retry run" })).toBeVisible()
  })

  it.each(["failed", "cancelled"] as const)(
    "offers Retry for a %s run and reconnects the restarted stream",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(JSON.stringify({ ...run, status: "running" }), {
            status: 202,
            headers: { "Content-Type": "application/json" },
          })
        )
      )
      act(() => useAppStore.getState().showRun({ ...run, status }))
      render(<StoredRunDetail />)
      const socketsBeforeRetry = MockWebSocket.instances.length

      expect(screen.getByRole("button", { name: "Retry run" })).toBeVisible()
      expect(screen.queryByRole("button", { name: "Cancel run" })).not.toBeInTheDocument()
      fireEvent.click(screen.getByRole("button", { name: "Retry run" }))

      await waitFor(() =>
        expect(useAppStore.getState().currentRun?.status).toBe("running")
      )
      expect(fetch).toHaveBeenCalledWith(
        "/api/runs/run-streaming/resume",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ answers: {} }),
        })
      )
      expect(useAppStore.getState().runs[0].status).toBe("running")
      expect(screen.getByRole("button", { name: "Cancel run" })).toBeVisible()
      await waitFor(() =>
        expect(MockWebSocket.instances.length).toBeGreaterThan(socketsBeforeRetry)
      )
    }
  )

  it("replays the failing stage and error when a failed run detail mounts", () => {
    render(<RunDetail run={{ ...run, status: "failed", phase: "CODEX_REVIEW" }} />)

    expect(MockWebSocket.instances).toHaveLength(1)
    MockWebSocket.instances[0].receive(
      event({
        type: "phase_change",
        phase: "CODEX_REVIEW",
        status: "failed",
      })
    )
    MockWebSocket.instances[0].receive(
      event({ type: "failed", error: "Reviewer timed out" })
    )

    const pipeline = screen.getByRole("list", { name: "Workflow stages" })
    expect(within(pipeline).getByText("Review").closest("li")).toHaveAttribute(
      "data-status",
      "failed"
    )
    expect(screen.getAllByText("Reviewer timed out").length).toBeGreaterThan(0)
  })

  it("loads questions after a paused event and returns to progress after resume", async () => {
    let finishResume: ((response: Response) => void) | undefined
    const resumeResponse = new Promise<Response>((resolve) => {
      finishResume = resolve
    })
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith("/artifacts/scoping_questions.json")) {
          const questions: ScopingQuestions = {
            round: 1,
            placeholder_token: "round-1-placeholder",
            questions: [
              {
                id: "Q1",
                question: "What is one row?",
                type: "text",
                options: null,
              },
            ],
          }
          return new Response(
            JSON.stringify(questions),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        }
        if (url.endsWith("/resume") && init?.method === "POST") {
          return resumeResponse
        }
        throw new Error(`Unexpected request: ${url}`)
      }
    )
    vi.stubGlobal("fetch", fetchMock)
    act(() => useAppStore.getState().showRun(run))
    render(<StoredRunDetail />)

    MockWebSocket.instances[0].receive(
      event({
        type: "paused",
        reason: "Scoping questions need answers",
        questions_artifact: "/runs/run-streaming/artifacts/scoping_questions.json",
      })
    )

    expect(
      await screen.findByRole("heading", { name: "Scoping questions" })
    ).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/runs/run-streaming/artifacts/scoping_questions.json"
    )
    fireEvent.change(screen.getByRole("textbox", { name: "What is one row?" }), {
      target: { value: "One source folder." },
    })
    fireEvent.click(screen.getByRole("button", { name: "Submit answers" }))

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/runs/run-streaming/resume",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            answers: { Q1: { value: "One source folder.", note: null } },
          }),
        })
      )
    )
    MockWebSocket.instances[0].receive(
      event({ type: "completed", final_xlsx: "/runs/run-streaming/output/final.xlsx" })
    )
    finishResume?.(
      new Response(
        JSON.stringify({ ...run, status: "running", phase: "AWAIT_SCOPING_ANSWERS" }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      )
    )
    await waitFor(() => expect(useAppStore.getState().scoping.status).toBe("ready"))

    expect(screen.getByRole("list", { name: "Workflow stages" })).toBeVisible()
    expect(useAppStore.getState().currentRun?.status).toBe("completed")
    expect(MockWebSocket.instances).toHaveLength(1)
  })
})
