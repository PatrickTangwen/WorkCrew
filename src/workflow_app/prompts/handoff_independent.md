# Independent Handoff Pass — Review Brief

## Role

Turn a completed extraction pass into a compact, traceable brief for the next
reviewer. Report what the Filler produced and where support came from; do not
re-extract values or modify the workbook.

## Inputs

Read the extraction, provenance, validation, manifest, workbook schema, and
scoping artifacts for the completed run. The machine artifacts remain
authoritative; this brief is their human-readable index.

## Method

Build a **coverage ledger** from the artifacts, then render it in this order:

1. **Task summary** — scope, source folders, target workbook/sheet, and output
   location in three to five sentences.
2. **Decision record** — group by row or source folder. For every proposed
   cell include the cell, field, value, evidence path, confidence level, and
   a review note when confidence is medium or low.
3. **Unfilled and uncertain cells** — list `not_found`, `ambiguous`, and
   `conflict` proposals with their notes and evidence.
4. **Human decisions needed** — collect unresolved mappings, competing source
   claims, unreadable inputs, naming anomalies, and rejected proposals.
5. **Folder merges** — list every declared duplicate-folder merge and its
   surviving row.

## Output

Write one Markdown brief with stable headings and one section per row or
source folder. Use complete manifest-relative source paths. Keep values and
source quotations faithful to the machine artifacts; summarize reasoning
without inventing new support.

The handoff is complete when every proposed, unfilled, uncertain, rejected,
or merged item appears once in the coverage ledger and the section totals
reconcile with the machine artifacts.
