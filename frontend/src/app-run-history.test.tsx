import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import App from "@/App"
import { useAppStore } from "@/store/use-app-store"

const apiMocks = vi.hoisted(() => ({
  getRun: vi.fn(),
  listRuns: vi.fn(),
}))

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...apiMocks,
}))

const summaries = [
  {
    run_id: "run-newer",
    status: "failed",
    started_at: "2026-08-09T12:00:00Z",
    duration: 4,
    source_name: "newer-source",
    workbook_name: "newer.xlsx",
  },
  {
    run_id: "run-older",
    status: "completed",
    started_at: "2026-08-08T10:00:00Z",
    duration: 90,
    source_name: "older-source",
    workbook_name: "older.xlsx",
  },
]

const olderRun = {
  run_id: "run-older",
  status: "completed",
  start_time: "2026-08-08T10:00:00Z",
  workspace_path: "/runs/run-older",
  phase: "FINALIZE",
  source_name: "older-source",
  workbook_name: "older.xlsx",
}

describe("run history", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState())
    apiMocks.listRuns.mockReset().mockResolvedValue(summaries)
    apiMocks.getRun.mockReset().mockResolvedValue(olderRun)
  })

  it("lists rich run cards and opens the selected historical run", async () => {
    render(<App />)

    const sidebar = screen.getByRole("complementary", { name: "Run history" })
    const runCards = await within(sidebar).findAllByRole("button", {
      name: /^Open run /,
    })
    expect(runCards.map((card) => card.getAttribute("aria-label"))).toEqual([
      "Open run run-newer",
      "Open run run-older",
    ])
    expect(within(sidebar).getByText(/^Failed ·/)).toBeVisible()
    expect(within(sidebar).getByText(/^Completed ·/)).toBeVisible()
    expect(within(sidebar).getByText("4s")).toBeVisible()
    expect(within(sidebar).getByText("1m 30s")).toBeVisible()
    expect(within(sidebar).getByText("older-source → older.xlsx")).toBeVisible()

    fireEvent.click(runCards[1])

    await waitFor(() => expect(apiMocks.getRun).toHaveBeenCalledWith("run-older"))
    expect(
      await screen.findByRole("heading", {
        name: "older-source → older.xlsx",
      })
    ).toBeVisible()
    expect(
      within(screen.getByRole("region", { name: "Run detail" })).getByText(
        "5 of 5 complete"
      )
    ).toBeVisible()
    expect(runCards[1]).toHaveAttribute("aria-current", "true")

    fireEvent.click(within(sidebar).getByRole("button", { name: "New run" }))
    expect(
      screen.getByRole("heading", { name: "What should this run produce?" })
    ).toBeVisible()
  })
})
