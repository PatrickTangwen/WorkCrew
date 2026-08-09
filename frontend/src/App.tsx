import { useEffect } from "react"
import { Files, Plus } from "lucide-react"

import { RunCreationForm } from "@/components/run-creation-form"
import { RunDetail } from "@/components/run-detail"
import { RunSidebar } from "@/components/run-sidebar"
import { Button } from "@/components/ui/button"
import { getRun, listRuns, type RunSummary } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

function App() {
  const view = useAppStore((state) => state.view)
  const currentRun = useAppStore((state) => state.currentRun)
  const runs = useAppStore((state) => state.runs)
  const historyStatus = useAppStore((state) => state.historyStatus)
  const historyError = useAppStore((state) => state.historyError)
  const openNewRun = useAppStore((state) => state.openNewRun)
  const showRun = useAppStore((state) => state.showRun)
  const startHistoryLoad = useAppStore((state) => state.startHistoryLoad)
  const receiveRuns = useAppStore((state) => state.receiveRuns)
  const failHistoryLoad = useAppStore((state) => state.failHistoryLoad)

  useEffect(() => {
    let ignore = false
    startHistoryLoad()
    void listRuns()
      .then((history) => {
        if (!ignore) receiveRuns(history)
      })
      .catch((cause: unknown) => {
        if (!ignore) {
          failHistoryLoad(
            cause instanceof Error ? cause.message : "Unable to load run history"
          )
        }
      })
    return () => {
      ignore = true
    }
  }, [failHistoryLoad, receiveRuns, startHistoryLoad])

  async function selectRun(run: RunSummary) {
    try {
      showRun(await getRun(run.run_id))
    } catch (cause) {
      failHistoryLoad(
        cause instanceof Error ? cause.message : "Unable to open the selected run"
      )
    }
  }

  return (
    <main className="min-h-svh bg-muted/30 lg:grid lg:grid-cols-[288px_minmax(0,1fr)]">
      <RunSidebar
        runs={runs}
        selectedRunId={view === "run" ? (currentRun?.run_id ?? null) : null}
        historyStatus={historyStatus}
        historyError={historyError}
        onNewRun={openNewRun}
        onSelect={(run) => void selectRun(run)}
      />

      <section
        aria-label={view === "run" ? "Run detail" : undefined}
        className="min-w-0 p-5 sm:p-8 lg:p-10"
      >
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
