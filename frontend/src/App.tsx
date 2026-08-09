import { CircleCheck, PanelsTopLeft, Server, Terminal } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useAppStore } from "@/store/use-app-store"

const checks = [
  { icon: PanelsTopLeft, label: "React interface", detail: "Vite + TypeScript" },
  { icon: Server, label: "Local backend", detail: "FastAPI + Uvicorn" },
  { icon: Terminal, label: "Single command", detail: "workflow ui" },
]

function App() {
  const status = useAppStore((state) => state.status)

  return (
    <main className="min-h-svh bg-[radial-gradient(circle_at_top_left,var(--color-muted),transparent_38%)] px-5 py-10 sm:px-8">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <header className="flex items-center justify-between border-b pb-5">
          <div className="flex items-center gap-3">
            <div className="grid size-9 place-items-center rounded-lg bg-foreground text-background">
              <PanelsTopLeft className="size-4" aria-hidden="true" />
            </div>
            <div>
              <p className="font-heading text-sm font-semibold">WorkCrew</p>
              <p className="text-xs text-muted-foreground">Document workflow</p>
            </div>
          </div>
          <Badge variant="outline" className="gap-1.5 bg-background/70">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            {status === "ready" ? "Local server ready" : "Starting"}
          </Badge>
        </header>

        <section className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-5">
            <Badge variant="secondary">V2 web UI foundation</Badge>
            <div className="space-y-3">
              <h1 className="max-w-xl font-heading text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
                Your workflow workspace is connected.
              </h1>
              <p className="max-w-lg text-base leading-7 text-muted-foreground">
                The local React interface and Python server are wired together.
                Run creation, progress, and artifacts arrive in the next UI slices.
              </p>
            </div>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CircleCheck className="size-4 text-emerald-600" aria-hidden="true" />
              The production bundle is ready for FastAPI.
            </div>
          </div>

          <Card className="bg-background/80 shadow-xl shadow-black/5 backdrop-blur">
            <CardHeader className="border-b">
              <CardTitle>Foundation status</CardTitle>
              <CardDescription>
                Everything required for the first frontend ticket is online.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              {checks.map(({ icon: Icon, label, detail }) => (
                <div
                  key={label}
                  className="flex items-center gap-3 rounded-lg border bg-background px-3 py-3"
                >
                  <div className="grid size-8 place-items-center rounded-md bg-muted">
                    <Icon className="size-4" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{label}</p>
                    <p className="text-xs text-muted-foreground">{detail}</p>
                  </div>
                  <CircleCheck
                    className="size-4 text-emerald-600"
                    aria-label="Ready"
                  />
                </div>
              ))}
            </CardContent>
          </Card>
        </section>
      </div>
    </main>
  )
}

export default App
