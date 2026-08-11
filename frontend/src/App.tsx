import { useEffect } from "react"

import { RunCreationForm } from "@/components/run-creation-form"
import { RunDetail } from "@/components/run-detail"
import { RunSidebar } from "@/components/run-sidebar"
import { TopBar } from "@/components/top-bar"
import { getRun, listRuns, type RunSummary } from "@/lib/api"
import { useAppStore } from "@/store/use-app-store"

function EmptyState({ onNewRun }: { onNewRun: () => void }) {
  return (
    <>
      <TopBar
        title={<span className="truncate text-sm font-medium text-ink">WorkCrew</span>}
      />
      <div className="grid flex-1 place-items-center px-8 pb-12">
        <div className="max-w-[440px] text-center">
          <h1 className="text-[33px] leading-[1.15] font-semibold tracking-[-0.02em] text-ink">
            Start with the working set.
          </h1>
          <p className="mt-3 text-sm leading-[1.65] text-pretty text-subtle">
            Select source documents, a workbook, and the rules that turn them into a
            traceable run. Agent runtimes may send task content to their configured
            services.
          </p>
          <button
            type="button"
            onClick={onNewRun}
            className="mt-6 h-[38px] cursor-pointer rounded-[9px] bg-brand px-[18px] text-[13.5px] font-medium text-white transition-colors hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            New run
          </button>
        </div>
      </div>
    </>
  )
}

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
    <main className="min-h-svh bg-paper lg:grid lg:grid-cols-[288px_minmax(0,1fr)]">
      <RunSidebar
        runs={runs}
        selectedRunId={view === "run" ? (currentRun?.run_id ?? null) : null}
        historyStatus={historyStatus}
        historyError={historyError}
        onBrand={openNewRun}
        onNewRun={openNewRun}
        onSelect={(run) => void selectRun(run)}
      />

      <section
        aria-label={view === "run" ? "Run detail" : undefined}
        className="flex min-h-svh min-w-0 flex-col"
      >
        {view === "new-run" && <RunCreationForm onCreated={showRun} />}
        {view === "run" && currentRun && <RunDetail run={currentRun} />}
        {view === "empty" && <EmptyState onNewRun={openNewRun} />}
      </section>
    </main>
  )
}

export default App
