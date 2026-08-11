# ADR 0035: Deliverables are exported to the source folder

Date: 2026-08-10

## Context

A finished run's outputs lived only inside its workspace, under a runs
root that defaults to `runs/` relative to the server's working directory
(`server.py`). The operator had to be told where that was, and the results
sat far away from the documents they were derived from.

Relocating the whole workspace into the source folder was considered and
rejected: `RunHistory` and `ArtifactCatalog` both discover runs by
globbing one runs root, so per-source workspaces would break run history
and artifact serving, and the source folder would accumulate input copies,
raw agent output, and SQLite state.

## Decision

The workspace layout and the runs root are unchanged. At the end of
FINALIZE, the run copies its deliverables into
`<source>/workcrew-output/<run_id>/`.

- The exported set is `artifacts.deliverable_entries()` — the same
  definition the app's artifact list publishes — so the exported folder
  and the Artifacts panel can never describe different sets of files.
  One definition, two consumers.
- The export is run-scoped. Deliverable file names are fixed
  (`final.xlsx`, `review_explorer_v2.html`, …), so a flat export at the
  source root would let a second run silently overwrite the first run's
  results.
- It runs after `record_run_finished` and after the run summary is
  written, so `run_summary.md` carries the closed run's status and is
  itself exported. A failing export therefore surfaces as a failed run
  with the workspace copy intact, not as a silent partial delivery.
- `copy_inputs` skips `workcrew-output` when it is an entry of the source
  root, so a later run on the same folder does not ingest the earlier
  run's deliverables as source documents. A directory of the same name
  deeper in the tree belongs to the operator and is copied.

The workspace-inside-the-source-folder guard (ADR-less, commit
`0ebe654`) still applies: the run workspace itself must stay outside the
source folder.

## Consequences

The operator finds every published artifact beside the documents that
produced it, without knowing where the runs root is. The source folder is
no longer read-only for the app: the invariant weakens from "the run
writes nothing into the source folder" to "the run modifies nothing that
was already in the source folder and adds one export directory", which is
what the walking-skeleton test now asserts and what the creation form now
tells the operator.
