import { useCallback, useEffect, useState, type RefObject } from "react"
import {
  ChevronRight,
  File,
  Folder,
  HardDrive,
  LoaderCircle,
  X,
} from "lucide-react"
import { Dialog } from "radix-ui"

import { Button } from "@/components/ui/button"
import { browseFiles, type BrowseListing } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

type FileBrowserModalProps = {
  open: boolean
  title: string
  mode: "directory" | "file"
  returnFocusRef: RefObject<HTMLElement | null>
  onClose: () => void
  onSelect: (path: string) => void
}

function joinPath(parent: string, name: string) {
  return `${parent.replace(/\/$/, "")}/${name}`
}

function FileBrowserModal({
  open,
  title,
  mode,
  returnFocusRef,
  onClose,
  onSelect,
}: FileBrowserModalProps) {
  const [listing, setListing] = useState<BrowseListing | null>(null)
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadDirectory = useCallback(
    async (path?: string, isCurrent: () => boolean = () => true) => {
      if (isCurrent()) {
        setLoading(true)
        setSelectedFile(null)
        setError(null)
      }
      try {
        const nextListing = await browseFiles(path)
        if (isCurrent()) setListing(nextListing)
      } catch (cause) {
        if (isCurrent()) {
          setError(cause instanceof Error ? cause.message : "Unable to browse files")
        }
      } finally {
        if (isCurrent()) setLoading(false)
      }
    },
    []
  )

  useEffect(() => {
    if (!open) return

    let cancelled = false
    void loadDirectory(undefined, () => !cancelled)
    return () => {
      cancelled = true
    }
  }, [loadDirectory, open])

  const breadcrumbs = listing
    ? [
        { label: "~", path: listing.root },
        ...listing.path
          .slice(listing.root.length)
          .split("/")
          .filter(Boolean)
          .map((segment, index, segments) => ({
            label: segment,
            path: joinPath(listing.root, segments.slice(0, index + 1).join("/")),
          })),
      ]
    : []

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-foreground/28 backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            returnFocusRef.current?.focus()
          }}
          onPointerDownOutside={(event) => event.preventDefault()}
          className="fixed top-1/2 left-1/2 z-50 flex max-h-[min(720px,90svh)] w-[calc(100%-2rem)] max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl shadow-black/15"
        >
        <header className="flex items-start justify-between gap-4 border-b px-5 py-4">
          <div>
            <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Home directory
            </p>
            <Dialog.Title asChild>
              <h2 className="mt-1 font-heading text-lg font-semibold">{title}</h2>
            </Dialog.Title>
          </div>
          <Dialog.Close asChild>
            <Button size="icon" variant="ghost" aria-label="Close file browser">
              <X />
            </Button>
          </Dialog.Close>
        </header>

        <nav aria-label="Current path" className="flex min-h-12 items-center gap-1 overflow-x-auto border-b bg-muted/35 px-4">
          {breadcrumbs.map((crumb, index) => (
            <div key={crumb.path} className="flex shrink-0 items-center gap-1">
              {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              <button
                type="button"
                onClick={() => void loadDirectory(crumb.path)}
                className="rounded px-1.5 py-1 font-mono text-xs hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                {crumb.label}
              </button>
            </div>
          ))}
        </nav>

        <div className="grid grid-cols-[minmax(0,1fr)] border-b bg-muted/20 px-4 py-2 text-[11px] font-medium tracking-wide text-muted-foreground uppercase sm:grid-cols-[minmax(0,1fr)_90px_150px]">
          <span>Name</span>
          <span className="hidden sm:block">Size</span>
          <span className="hidden sm:block">Modified</span>
        </div>

        <div className="min-h-64 flex-1 overflow-y-auto p-2">
          {loading && (
            <div className="grid min-h-48 place-items-center text-sm text-muted-foreground">
              <span className="flex items-center gap-2">
                <LoaderCircle className="animate-spin" /> Reading folder…
              </span>
            </div>
          )}
          {!loading && error && (
            <div className="m-3 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {!loading && !error && listing?.entries.length === 0 && (
            <div className="grid min-h-48 place-items-center text-sm text-muted-foreground">
              This folder is empty.
            </div>
          )}
          {!loading &&
            !error &&
            listing?.entries.map((entry) => {
              const entryPath = joinPath(listing.path, entry.name)
              const isSelected = selectedFile === entryPath
              return (
                <button
                  key={entry.name}
                  type="button"
                  onClick={() => {
                    if (entry.type === "directory") void loadDirectory(entryPath)
                    else if (mode === "file") setSelectedFile(entryPath)
                  }}
                  disabled={entry.type === "file" && mode === "directory"}
                  className={cn(
                    "grid w-full grid-cols-[minmax(0,1fr)] items-center rounded-lg px-2 py-2.5 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none sm:grid-cols-[minmax(0,1fr)_90px_150px]",
                    isSelected ? "bg-foreground text-background" : "hover:bg-muted",
                    entry.type === "file" && mode === "directory" && "cursor-default opacity-45"
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2.5">
                    {entry.type === "directory" ? (
                      <Folder className="shrink-0" />
                    ) : (
                      <File className="shrink-0" />
                    )}
                    <span className="truncate font-medium">{entry.name}</span>
                  </span>
                  <span className="hidden font-mono text-xs opacity-70 sm:block">
                    {entry.type === "directory" ? "—" : formatBytes(entry.size)}
                  </span>
                  <span className="hidden truncate font-mono text-xs opacity-70 sm:block">
                    {new Date(entry.modified).toLocaleString()}
                  </span>
                </button>
              )
            })}
        </div>

        <footer className="flex items-center justify-between gap-4 border-t bg-muted/20 px-5 py-4">
          <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
            <HardDrive className="shrink-0" />
            <span className="hidden truncate font-mono sm:block">
              {selectedFile ?? listing?.path ?? "Loading home…"}
            </span>
          </div>
          <div className="flex shrink-0 gap-2">
            <Dialog.Close asChild>
              <Button variant="outline">Cancel</Button>
            </Dialog.Close>
            <Dialog.Close asChild>
              <Button
                disabled={
                  loading || (mode === "file" ? selectedFile === null : listing === null)
                }
                onClick={() => {
                  const selected = mode === "file" ? selectedFile : listing?.path
                  if (selected) onSelect(selected)
                }}
              >
                {mode === "directory" ? "Select folder" : "Select file"}
              </Button>
            </Dialog.Close>
          </div>
        </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export { FileBrowserModal }
