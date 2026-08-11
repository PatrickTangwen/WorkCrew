# ADR 0039: The UI presents a curated artifact view

Status: accepted
Date: 2026-08-11

Supersedes only ADR 0035's requirement that the Artifacts panel display the
same set as the source-folder export. The export location, run scoping, and
input-copy exclusions in ADR 0035 remain in force.

## Context

The artifact catalog is an audit and reproducibility surface. It includes
intermediate JSON, scoping records, manifests, and reports that are useful for
diagnosis but make the normal completed-run view harder to scan. Removing those
files from the catalog or export would improve the UI by weakening the run
record.

An evaluation may also be generated after FINALIZE. It belongs in the run
workspace and catalog, but FINALIZE's source-folder export is a completion-time
snapshot rather than a directory that later commands silently mutate.

## Decision

The backend artifact catalog remains complete, and FINALIZE exports that
complete catalog into `<source>/workcrew-output/<run_id>/`. The UI applies a
curated projection in this order:

1. `final.xlsx`
2. `human_review.md`, when present
3. the final English review explorer, preferring
   `review_explorer_v2.html` over `review_explorer.html`
4. the final Chinese review explorer, preferring
   `review_explorer_zh_v2.html` over `review_explorer_zh.html`
5. `run_summary.md`
6. `evaluation.md`, when present

The API continues to list and serve every supported artifact. Evaluation output
created after FINALIZE appears through the API and UI but does not retroactively
rewrite the completion-time source-folder export.

## Consequences

Operators see the files needed to use or assess the result without navigating
engine internals. Debugging and audit consumers retain the complete record via
the API and exported snapshot. A UI omission means "not useful in the normal
completed-run view," not "private" or "unsupported."
