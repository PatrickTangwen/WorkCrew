import { Files, PanelsTopLeft, Plus, ShieldCheck } from "lucide-react"

import { RunCreationForm } from "@/components/run-creation-form"
import { RunDetail } from "@/components/run-detail"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useAppStore } from "@/store/use-app-store"

function App() {
  const view = useAppStore((state) => state.view)
  const currentRun = useAppStore((state) => state.currentRun)
  const openNewRun = useAppStore((state) => state.openNewRun)
  const showRun = useAppStore((state) => state.showRun)

  return (
    <main className="min-h-svh bg-muted/30 lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="flex border-b bg-background lg:min-h-svh lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex flex-1 items-center gap-3 px-4 py-3 lg:flex-none lg:border-b lg:px-5 lg:py-5">
          <div className="grid size-9 place-items-center rounded-lg bg-foreground text-background">
            <PanelsTopLeft className="size-4" aria-hidden="true" />
          </div>
          <div>
            <p className="font-heading text-sm font-semibold">WorkCrew</p>
            <p className="text-xs text-muted-foreground">Local workflow desk</p>
          </div>
        </div>

        <div className="p-3 lg:p-4">
          <Button onClick={openNewRun} className="w-full">
            <Plus /> New run
          </Button>
        </div>

        <div className="hidden min-h-0 flex-1 px-3 lg:block">
          <p className="px-2 pb-2 text-[10px] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
            Current
          </p>
          {currentRun ? (
            <button
              type="button"
              onClick={() => showRun(currentRun)}
              className="w-full rounded-xl border bg-muted/30 p-3 text-left transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs font-medium">{currentRun.run_id}</span>
                <span className="size-2 shrink-0 rounded-full bg-emerald-500" aria-label="Running" />
              </div>
              <p className="mt-2 truncate text-xs text-muted-foreground">{currentRun.workbook_name}</p>
            </button>
          ) : (
            <div className="rounded-xl border border-dashed px-3 py-4 text-xs leading-5 text-muted-foreground">
              No run selected.
            </div>
          )}
        </div>

        <div className="hidden border-t p-4 lg:block">
          <Badge variant="outline" className="gap-1.5 bg-background">
            <ShieldCheck /> Local only
          </Badge>
        </div>
      </aside>

      <section className="min-w-0 p-5 sm:p-8 lg:p-10">
        {view === "new-run" && <RunCreationForm onCreated={showRun} />}
        {view === "run" && currentRun && <RunDetail run={currentRun} />}
        {view === "empty" && (
          <div className="grid min-h-[calc(100svh-110px)] place-items-center lg:min-h-[calc(100svh-80px)]">
            <div className="max-w-md text-center">
              <div className="mx-auto grid size-14 place-items-center rounded-2xl border bg-background shadow-sm">
                <Files className="size-6" aria-hidden="true" />
              </div>
              <h1 className="mt-5 font-heading text-3xl font-semibold tracking-tight">
                Start with the working set.
              </h1>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                Select source documents, a workbook, and the rules that turn them into a traceable run.
              </p>
              <Button onClick={openNewRun} className="mt-6">
                <Plus /> New run
              </Button>
            </div>
          </div>
        )}
      </section>
    </main>
  )
}

export default App
