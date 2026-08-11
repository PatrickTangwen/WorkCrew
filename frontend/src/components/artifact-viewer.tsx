import { useEffect, useState } from "react"
import Markdown from "react-markdown"
import { Download, ExternalLink, File, LoaderCircle } from "lucide-react"

import {
  artifactUrl,
  listArtifacts,
  readArtifactText,
  type ArtifactSummary,
} from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

function userFacingArtifacts(items: ArtifactSummary[]) {
  const byName = new Map(items.map((artifact) => [artifact.name, artifact]))
  const finalReview = byName.has("review_explorer_v2.html")
    ? "review_explorer_v2.html"
    : "review_explorer.html"
  const finalReviewZh = byName.has("review_explorer_zh_v2.html")
    ? "review_explorer_zh_v2.html"
    : "review_explorer_zh.html"
  const displayOrder = [
    "final.xlsx",
    "human_review.md",
    finalReview,
    finalReviewZh,
    "run_summary.md",
    "evaluation.md",
  ]

  return displayOrder.flatMap((name) => {
    const artifact = byName.get(name)
    return artifact ? [artifact] : []
  })
}

function TextArtifactPreview({
  artifact,
  runId,
}: {
  artifact: ArtifactSummary
  runId: string
}) {
  const [text, setText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setText(null)
    setError(null)
    void readArtifactText(runId, artifact.name)
      .then((content) => {
        if (!cancelled) setText(content)
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Unable to read artifact")
        }
      })
    return () => {
      cancelled = true
    }
  }, [artifact.name, runId])

  if (error) {
    return (
      <p className="rounded-[9px] border border-bad-line bg-bad-wash p-3 text-sm text-bad">
        {error}
      </p>
    )
  }
  if (text === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-faint">
        <LoaderCircle className="size-4 animate-spin" /> Loading preview…
      </p>
    )
  }
  if (artifact.type === "md") {
    return (
      <article className="max-w-[600px] space-y-3 text-[12.5px] leading-[1.75] text-body [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-line [&_blockquote]:pl-4 [&_code]:rounded [&_code]:bg-line-soft [&_code]:px-1 [&_code]:font-mono [&_code]:text-[11px] [&_h1]:text-[19px] [&_h1]:font-semibold [&_h1]:tracking-[-0.01em] [&_h1]:text-ink [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-ink [&_h3]:text-[13px] [&_h3]:font-semibold [&_h3]:text-ink [&_li]:ml-5 [&_ol]:list-decimal [&_pre]:overflow-x-auto [&_pre]:rounded-[10px] [&_pre]:border [&_pre]:border-line [&_pre]:bg-shell [&_pre]:p-4 [&_ul]:list-disc">
        <Markdown>{text}</Markdown>
      </article>
    )
  }
  return (
    <pre className="overflow-x-auto rounded-[10px] border border-line bg-shell p-4 font-mono text-[11px] leading-[1.85] text-body">
      {text}
    </pre>
  )
}

function WorkbookPreview({ artifact, runId }: { artifact: ArtifactSummary; runId: string }) {
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle")

  useEffect(() => setCopyStatus("idle"), [artifact.name])

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(artifact.path)
      setCopyStatus("copied")
    } catch {
      setCopyStatus("failed")
    }
  }

  return (
    <div className="grid min-h-70 place-items-center rounded-xl border border-dashed border-line-strong bg-paper p-6 text-center">
      <div>
        <span className="inline-grid size-11 place-items-center rounded-[11px] bg-ok-surface font-mono text-[10px] font-medium text-ok-ink">
          XLSX
        </span>
        <p className="mt-3.5 text-[13.5px] font-medium text-ink">Final workbook</p>
        <p
          title={artifact.path}
          className="mt-1.5 max-w-lg truncate font-mono text-[11px] text-faint"
        >
          {artifact.path}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <a
            href={artifactUrl(runId, artifact.name)}
            download={artifact.name}
            aria-label={`Download ${artifact.name}`}
            className="inline-flex h-[35px] items-center justify-center rounded-[9px] bg-brand px-4 text-[12.5px] font-medium text-white transition-colors hover:bg-brand/90"
          >
            Download {artifact.name}
          </a>
          <button
            type="button"
            onClick={() => void copyPath()}
            className="h-[35px] cursor-pointer rounded-[9px] border border-line-dash bg-surface px-3.5 text-[12.5px] font-medium text-ink transition-colors hover:bg-shell"
          >
            {copyStatus === "copied" ? "Path copied" : "Copy file path"}
          </button>
        </div>
        {copyStatus === "failed" && (
          <p className="mt-2 text-xs text-bad">Unable to copy path</p>
        )}
      </div>
    </div>
  )
}

function ArtifactPreview({
  artifact,
  runId,
}: {
  artifact: ArtifactSummary
  runId: string
}) {
  const [previewHeight, setPreviewHeight] = useState(480)

  if (artifact.type === "html") {
    return (
      <div>
        <div className="mb-3 flex items-center gap-3">
          <label className="flex items-center gap-3 text-[11px] text-faint">
            Preview height
            <input
              type="range"
              aria-label="Preview height"
              min="320"
              max="900"
              step="20"
              value={previewHeight}
              onChange={(event) => setPreviewHeight(Number(event.target.value))}
              className="w-[170px] accent-brand"
            />
          </label>
          <span className="font-mono text-[11px] text-subtle">{previewHeight}px</span>
        </div>
        <iframe
          title={`${artifact.name} preview`}
          src={artifactUrl(runId, artifact.name)}
          className="w-full rounded-[10px] border border-line bg-white"
          style={{ height: `${previewHeight}px` }}
        />
      </div>
    )
  }

  if (artifact.type === "md" || artifact.type === "json") {
    return <TextArtifactPreview artifact={artifact} runId={runId} />
  }

  return <WorkbookPreview artifact={artifact} runId={runId} />
}

function ArtifactViewer({ runId }: { runId: string }) {
  const [artifacts, setArtifacts] = useState<ArtifactSummary[] | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setArtifacts(null)
    setSelectedName(null)
    setError(null)
    void listArtifacts(runId)
      .then((items) => {
        if (cancelled) return
        const visibleItems = userFacingArtifacts(items)
        setArtifacts(visibleItems)
        setError(null)
        setSelectedName((current) =>
          visibleItems.some((artifact) => artifact.name === current)
            ? current
            : (visibleItems[0]?.name ?? null)
        )
      })
      .catch((cause) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "Unable to list artifacts")
        }
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  const selected = artifacts?.find((artifact) => artifact.name === selectedName)
  const total = artifacts?.reduce((bytes, artifact) => bytes + artifact.size, 0) ?? 0

  return (
    <section className="overflow-hidden rounded-[14px] border border-line bg-surface shadow-[0_1px_3px_rgba(31,30,28,.05)]">
      <div className="flex items-baseline justify-between gap-3 border-b border-line-soft px-5 py-[15px]">
        <p className="text-[13px] font-medium text-ink">Artifacts</p>
        {artifacts !== null && artifacts.length > 0 && (
          <span className="font-mono text-[11px] text-faint">
            {artifacts.length} files · {formatBytes(total)}
          </span>
        )}
      </div>

      {artifacts === null && error === null && (
        <p className="flex min-h-40 items-center justify-center gap-2 text-sm text-faint">
          <LoaderCircle className="size-4 animate-spin" /> Loading artifacts…
        </p>
      )}
      {error && (
        <p className="m-4 rounded-[9px] border border-bad-line bg-bad-wash p-3 text-sm text-bad">
          {error}
        </p>
      )}
      {artifacts?.length === 0 && (
        <p className="grid min-h-40 place-items-center text-sm text-faint">
          No artifacts available.
        </p>
      )}

      {artifacts && artifacts.length > 0 && (
        <div className="grid min-h-90 grid-cols-[238px_minmax(0,1fr)]">
          <ul
            aria-label="Artifacts"
            className="flex flex-col gap-[3px] border-r border-line-soft bg-shell p-2"
          >
            {artifacts.map((artifact) => {
              const chosen = artifact.name === selectedName
              return (
                <li key={artifact.name}>
                  <button
                    type="button"
                    onClick={() => setSelectedName(artifact.name)}
                    aria-label={`Preview ${artifact.name}`}
                    aria-current={chosen ? "true" : undefined}
                    className={cn(
                      "flex w-full cursor-pointer items-center gap-2.5 rounded-[9px] px-2.5 py-[9px] text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      chosen ? "bg-ink" : "hover:bg-raise"
                    )}
                  >
                    <span
                      className={cn(
                        "grid size-[30px] shrink-0 place-items-center rounded-[7px] font-mono text-[8.5px] font-medium tracking-[0.04em] uppercase",
                        chosen ? "bg-surface/14 text-surface" : "bg-line text-subtle"
                      )}
                    >
                      {artifact.type}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          "block truncate text-xs font-medium",
                          chosen ? "text-surface" : "text-ink"
                        )}
                      >
                        {artifact.name}
                      </span>
                      <span
                        className={cn(
                          "mt-0.5 block font-mono text-[10px]",
                          chosen ? "text-surface/55" : "text-ghost"
                        )}
                      >
                        {formatBytes(artifact.size)}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>

          <div className="flex min-w-0 flex-col" aria-live="polite">
            {selected && (
              <>
                <div className="flex items-center justify-between gap-3 border-b border-line-soft px-[18px] py-3">
                  <span className="flex min-w-0 items-center gap-2">
                    <File className="size-3.5 shrink-0 text-faint" aria-hidden="true" />
                    <span className="truncate font-mono text-[11.5px] font-medium text-body">
                      {selected.name}
                    </span>
                  </span>
                  <span className="flex shrink-0 gap-4 text-[11.5px] font-medium">
                    <a
                      href={artifactUrl(runId, selected.name)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-body hover:text-ink"
                    >
                      <ExternalLink className="size-3.5 shrink-0" aria-hidden="true" />
                      Open in new tab
                    </a>
                    <a
                      href={artifactUrl(runId, selected.name)}
                      download={selected.name}
                      className="inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-body hover:text-ink"
                    >
                      <Download className="size-3.5 shrink-0" aria-hidden="true" />
                      Download
                    </a>
                  </span>
                </div>
                <div className="min-w-0 flex-1 p-[18px]">
                  <ArtifactPreview artifact={selected} runId={runId} />
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

export { ArtifactViewer }
