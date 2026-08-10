import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { useRef, useState } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { FileBrowserModal } from "@/components/file-browser-modal"
import { browseFiles } from "@/lib/api"

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>()
  return {
    ...original,
    browseFiles: vi.fn(),
  }
})

function FileBrowserHarness() {
  const [open, setOpen] = useState(false)
  const openerRef = useRef<HTMLButtonElement>(null)

  return (
    <>
      <button ref={openerRef} type="button" onClick={() => setOpen(true)}>
        Choose source
      </button>
      <button type="button">Background action</button>
      <FileBrowserModal
        open={open}
        title="Choose source folder"
        mode="directory"
        returnFocusRef={openerRef}
        onClose={() => setOpen(false)}
        onSelect={() => undefined}
      />
    </>
  )
}

async function openFileBrowser() {
  const opener = screen.getByRole("button", { name: "Choose source" })
  opener.focus()
  fireEvent.click(opener)
  const dialog = await screen.findByRole("dialog")
  return { dialog, opener }
}

describe("FileBrowserModal keyboard access", () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.mocked(browseFiles).mockResolvedValue({
      path: "/home/operator",
      root: "/home/operator",
      entries: [
        {
          name: "source",
          type: "directory",
          size: 0,
          modified: "2026-08-10T12:00:00Z",
        },
      ],
    })
  })

  it("moves initial focus into the dialog", async () => {
    render(<FileBrowserHarness />)
    const { dialog } = await openFileBrowser()

    await waitFor(() =>
      expect(
        within(dialog).getByRole("button", { name: "Close file browser" })
      ).toHaveFocus()
    )
  })

  it("contains forward and reverse tab navigation", async () => {
    render(<FileBrowserHarness />)
    const { dialog } = await openFileBrowser()
    await screen.findByRole("button", { name: /^source/ })

    const enabledButtons = within(dialog)
      .getAllByRole("button")
      .filter((button) => !button.hasAttribute("disabled"))
    const first = enabledButtons[0]
    const last = enabledButtons.at(-1)!

    first.focus()
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true })
    expect(last).toHaveFocus()

    fireEvent.keyDown(last, { key: "Tab" })
    expect(first).toHaveFocus()
  })

  it("closes on Escape and restores focus to the exact opener", async () => {
    render(<FileBrowserHarness />)
    const { opener } = await openFileBrowser()

    fireEvent.keyDown(document.activeElement!, { key: "Escape" })

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument())
    expect(opener).toHaveFocus()
  })

  it("keeps focus out of background controls while open", async () => {
    render(<FileBrowserHarness />)
    const { dialog } = await openFileBrowser()
    const background = screen.getByText("Background action")

    background.focus()

    await waitFor(() =>
      expect(dialog).toContainElement(document.activeElement as HTMLElement | null)
    )
  })
})
