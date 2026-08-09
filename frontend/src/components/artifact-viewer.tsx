import { useEffect, useState } from "react"
import Markdown from "react-markdown"
import {
  Check,
  Copy,
  Download,
  ExternalLink,
  File,
  LoaderCircle,
  PackageOpen,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  artifactUrl,
  listArtifacts,
  readArtifactText,
  type ArtifactSummary,
} from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

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
      <p className="rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
        {error}
      </p>
    )
  }
  if (text === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="animate-spin" /> Loading preview…
      </p>
    )
  }
  if (artifact.type === "md") {
    return (
      <article className="max-w-none space-y-3 text-sm leading-7 [&_a]:underline [&_blockquote]:border-l-2 [&_blockquote]:pl-4 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_h1]:font-heading [&_h1]:text-2xl [&_h1]:font-semibold [&_h2]:font-heading [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_p]:text-foreground/85 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-4 [&_ul]:list-disc">
        <Markdown>{text}</Markdown>
      </article>
    )
  }
  return (
    <pre className="overflow-x-auto rounded-lg bg-muted p-4 font-mono text-xs leading-6">
      {text}
    </pre>
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
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "failed">("idle")
  const url = artifactUrl(runId, artifact.name)

  useEffect(() => setCopyStatus("idle"), [artifact.name])

  if (artifact.type === "html") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-3 text-xs text-muted-foreground">
            Preview height
            <input
              type="range"
              aria-label="Preview height"
              min="320"
              max="900"
              step="20"
              value={previewHeight}
              onChange={(event) => setPreviewHeight(Number(event.target.value))}
            />
            <span className="w-12 font-mono">{previewHeight}px</span>
          </label>
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-xs font-medium underline underline-offset-4"
          >
            <ExternalLink /> Open in new tab
          </a>
        </div>
        <iframe
          title={`${artifact.name} preview`}
          src={url}
          className="w-full rounded-lg border bg-white"
          style={{ height: `${previewHeight}px` }}
        />
      </div>
    )
  }

  if (artifact.type === "md" || artifact.type === "json") {
    return <TextArtifactPreview artifact={artifact} runId={runId} />
  }

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(artifact.path)
      setCopyStatus("copied")
    } catch {
      setCopyStatus("failed")
    }
  }

  return (
    <div className="grid min-h-56 place-items-center rounded-xl border border-dashed bg-muted/18 p-6 text-center">
      <div>
        <Download className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 font-medium">Final workbook</p>
        <p className="mt-1 max-w-lg truncate font-mono text-xs text-muted-foreground" title={artifact.path}>
          {artifact.path}
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <a
            href={url}
            download={artifact.name}
            className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/88"
            aria-label={`Download ${artifact.name}`}
          >
            <Download /> Download {artifact.name}
          </a>
          <Button variant="outline" onClick={() => void copyPath()}>
            {copyStatus === "copied" ? <Check /> : <Copy />}
            Copy file path
          </Button>
        </div>
        {copyStatus === "copied" && (
          <p className="mt-2 text-xs text-muted-foreground">Path copied</p>
        )}
        {copyStatus === "failed" && (
          <p className="mt-2 text-xs text-destructive">Unable to copy path</p>
        )}
      </div>
    </div>
  )
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
        setArtifacts(items)
        setError(null)
        setSelectedName((current) =>
          items.some((artifact) => artifact.name === current)
            ? current
            : (items[0]?.name ?? null)
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

  return (
    <Card className="overflow-hidden bg-background">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2">
          <PackageOpen className="size-4" /> Artifacts
        </CardTitle>
        <CardDescription>Inspect generated reports and download the final workbook.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {artifacts === null && error === null && (
          <p className="flex min-h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="animate-spin" /> Loading artifacts…
          </p>
        )}
        {error && (
          <p className="m-4 rounded-lg border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </p>
        )}
        {artifacts?.length === 0 && (
          <p className="grid min-h-40 place-items-center text-sm text-muted-foreground">
            No artifacts available.
          </p>
        )}
        {artifacts && artifacts.length > 0 && (
          <div className="grid min-h-80 lg:grid-cols-[17rem_minmax(0,1fr)]">
            <ul aria-label="Artifacts" className="border-b p-2 lg:border-r lg:border-b-0">
              {artifacts.map((artifact) => (
                <li key={artifact.name}>
                  <button
                    type="button"
                    onClick={() => setSelectedName(artifact.name)}
                    aria-label={`Preview ${artifact.name}`}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                      artifact.name === selectedName
                        ? "bg-foreground text-background"
                        : "hover:bg-muted"
                    )}
                  >
                    <File className="size-4 shrink-0" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{artifact.name}</span>
                      <span className="mt-0.5 block font-mono text-[11px] opacity-65">
                        {formatBytes(artifact.size)}
                      </span>
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        "uppercase",
                        artifact.name === selectedName && "border-background/35 text-background"
                      )}
                    >
                      {artifact.type}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
            <section className="min-w-0 p-4" aria-live="polite">
              {selected && <ArtifactPreview artifact={selected} runId={runId} />}
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export { ArtifactViewer }
