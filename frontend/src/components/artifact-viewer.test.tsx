import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { RunDetail } from "@/components/run-detail"

const apiMocks = vi.hoisted(() => ({
  listArtifacts: vi.fn(),
  readArtifactText: vi.fn(),
}))

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...apiMocks,
}))

const run = {
  run_id: "run-completed",
  status: "completed" as const,
  start_time: "2026-08-09T12:00:00Z",
  finished_at: null,
  workspace_path: "/runs/run-completed",
  phase: "FINALIZE",
  source_name: "source",
  workbook_name: "template.xlsx",
}

const artifacts = [
  {
    name: "review_explorer.html",
    type: "html",
    size: 1100,
    path: "/runs/run-completed/artifacts/review_explorer.html",
  },
  {
    name: "review_explorer_v2.html",
    type: "html",
    size: 1200,
    path: "/runs/run-completed/artifacts/review_explorer_v2.html",
  },
  {
    name: "review_explorer_zh_v2.html",
    type: "html",
    size: 1250,
    path: "/runs/run-completed/artifacts/review_explorer_zh_v2.html",
  },
  {
    name: "human_review.md",
    type: "md",
    size: 90,
    path: "/runs/run-completed/artifacts/human_review.md",
  },
  {
    name: "run_summary.md",
    type: "md",
    size: 80,
    path: "/runs/run-completed/artifacts/run_summary.md",
  },
  {
    name: "final.xlsx",
    type: "xlsx",
    size: 2048,
    path: "/runs/run-completed/output/final.xlsx",
  },
  {
    name: "evaluation.md",
    type: "md",
    size: 24,
    path: "/runs/run-completed/artifacts/evaluation.md",
  },
  {
    name: "extraction.json",
    type: "json",
    size: 24,
    path: "/runs/run-completed/artifacts/extraction.json",
  },
  {
    name: "handoff.md",
    type: "md",
    size: 80,
    path: "/runs/run-completed/artifacts/handoff.md",
  },
]

describe("artifact viewer", () => {
  const writeText = vi.fn()

  afterEach(cleanup)

  beforeEach(() => {
    apiMocks.listArtifacts.mockReset().mockResolvedValue(artifacts)
    apiMocks.readArtifactText.mockReset().mockImplementation(async (_runId, name) =>
      name === "run_summary.md" ? "# Run summary\n\nComplete." : "# Evaluation"
    )
    writeText.mockReset().mockResolvedValue(undefined)
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    })
  })

  it("shows only user-facing deliverables in priority order", async () => {
    render(<RunDetail run={run} />)

    expect(await screen.findByRole("list", { name: "Artifacts" })).toBeVisible()
    expect(
      screen
        .getAllByRole("button", { name: /^Preview / })
        .map((button) => button.getAttribute("aria-label"))
    ).toEqual([
      "Preview final.xlsx",
      "Preview human_review.md",
      "Preview review_explorer_v2.html",
      "Preview review_explorer_zh_v2.html",
      "Preview run_summary.md",
      "Preview evaluation.md",
    ])
    expect(
      screen.queryByRole("button", { name: "Preview extraction.json" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Preview handoff.md" })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Preview review_explorer.html" })
    ).not.toBeInTheDocument()
    expect(screen.getAllByText("1.2 KB")).toHaveLength(2)
    expect(screen.getByRole("link", { name: "Download final.xlsx" })).toHaveAttribute(
      "download",
      "final.xlsx"
    )

    fireEvent.click(
      screen.getByRole("button", { name: "Preview review_explorer_v2.html" })
    )
    const frame = screen.getByTitle("review_explorer_v2.html preview")
    expect(frame).toHaveAttribute(
      "src",
      "/api/runs/run-completed/artifacts/review_explorer_v2.html"
    )
    expect(screen.getByRole("link", { name: "Open in new tab" })).toHaveAttribute(
      "target",
      "_blank"
    )
    fireEvent.change(screen.getByRole("slider", { name: "Preview height" }), {
      target: { value: "720" },
    })
    expect(frame).toHaveStyle({ height: "720px" })

    fireEvent.click(screen.getByRole("button", { name: "Preview run_summary.md" }))
    expect(await screen.findByRole("heading", { name: "Run summary" })).toBeVisible()
    expect(apiMocks.readArtifactText).toHaveBeenCalledWith(
      "run-completed",
      "run_summary.md"
    )

    fireEvent.click(screen.getByRole("button", { name: "Preview final.xlsx" }))
    expect(screen.getByRole("link", { name: "Download final.xlsx" })).toHaveAttribute(
      "download",
      "final.xlsx"
    )
    fireEvent.click(screen.getByRole("button", { name: "Copy file path" }))
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        "/runs/run-completed/output/final.xlsx"
      )
    )
    expect(screen.getByText("Path copied")).toBeVisible()
  })

  it("clears the previous run while loading a different run", async () => {
    let resolveNextRun: (items: typeof artifacts) => void = () => undefined
    apiMocks.listArtifacts
      .mockResolvedValueOnce(artifacts)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNextRun = resolve
          })
      )
    const { rerender } = render(<RunDetail run={run} />)
    expect(
      await screen.findByRole("button", { name: "Preview evaluation.md" })
    ).toBeVisible()

    rerender(<RunDetail run={{ ...run, run_id: "run-next" }} />)

    expect(
      screen.queryByRole("button", { name: "Preview evaluation.md" })
    ).not.toBeInTheDocument()
    expect(screen.getByText("Loading artifacts…")).toBeVisible()

    resolveNextRun([
      {
        name: "run_summary.md",
        type: "md",
        size: 10,
        path: "/runs/run-next/artifacts/run_summary.md",
      },
    ])
    expect(
      await screen.findByRole("button", { name: "Preview run_summary.md" })
    ).toBeVisible()
  })

  it("clears an old artifact error when the run changes", async () => {
    apiMocks.listArtifacts
      .mockRejectedValueOnce(new Error("Old run failed"))
      .mockResolvedValueOnce(artifacts)
    const { rerender } = render(<RunDetail run={run} />)
    expect(await screen.findByText("Old run failed")).toBeVisible()

    rerender(<RunDetail run={{ ...run, run_id: "run-next" }} />)

    expect(screen.queryByText("Old run failed")).not.toBeInTheDocument()
    expect(await screen.findByRole("list", { name: "Artifacts" })).toBeVisible()
  })
})
