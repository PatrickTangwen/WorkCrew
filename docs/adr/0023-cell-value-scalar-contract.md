# 0023 — CellValue scalar contract for cell values

Status: accepted (amends plan section 18's literal `Any`; supersedes
ADR 0018's empty-schema normalization)
Date: 2026-08-09
Ticket: none (debt recorded in #11's closing comment)

## Context

Plan section 18 writes cell-value fields as `value: Any | None`. The
`Any` produced an empty JSON schema, which OpenAI's strict
structured-output dialect rejects, so `codex.strict_schema` carried a
special case rewriting empty schemas into a hardcoded scalar union —
wire knowledge living in an adapter instead of the contract.

## Decisions

### Cell values are a shared scalar alias

`models/values.py` defines `CellValue = str | int | float | bool |
None`, used by `CellProposal.value`,
`ReviewFinding.current_value/recommended_value`,
`RevisionDecision.original_value/proposed_value`, and
`ProvenanceEntry.value`. Workbook cell values are JSON scalars end to
end — dates travel as ISO strings. The contracts now emit the
concrete union in their own JSON schemas, and the adapter special
case is deleted (the corresponding sentence in ADR 0018 is
superseded).

### A structured value is a contract violation, retried at the wire

An agent returning an object or array as a cell value now fails
contract validation inside `run_agent` and consumes a lenient retry
(plan section 37) instead of reaching the deterministic layers.

### Persisted-artifact re-validation fails closed

Artifacts are re-validated on load (resume, downstream nodes). A
pre-CellValue run whose persisted `extraction.json` /
`revision.json` holds a structured value — legal under the old `Any`
wire contract — no longer re-validates: such a run must be completed
with pre-change code. Accepted deliberately: the strict contract is
the protection, the deterministic value validators always rejected
structured values from the workbook anyway, and unlike ADR 0016's
audit-column migration (which affected every pre-#9 run) this touches
only runs that were already carrying rogue values mid-crash.
