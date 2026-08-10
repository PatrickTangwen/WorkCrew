import { act, cleanup, render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RunDetail } from "@/components/run-detail"
import type { RunRecord, WorkflowEvent } from "@/lib/api"
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
})
