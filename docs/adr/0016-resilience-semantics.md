# 0016 — Resilience semantics: replay, retries, fail-hard vs fail-soft

Status: accepted (amends 0011)
Date: 2026-08-08
Ticket: #9 (crash resume, idempotent re-application, lenient retries)

## Decisions

### Idempotent replays write the value again (amends ADR 0011)

ADR 0011's "identical replays skip without side effects" assumed the
workbook still held the value. A crash-resume re-runs the whole
mutating node — WRITE_DRAFT re-copies the template — so a skip would
silently lose every previously applied cell. A replay (same run, cell,
actor, source, same value) now re-writes the value, reports
`status="applied"` with `replayed=True`, and adds no audit record:
downstream consumers see exactly the outcomes of an uninterrupted run,
and the audit trail stays free of duplicates. Differing values still
raise MutationConflictError before any save or audit.

### Audit lands before the workbook save

The mutation batch records its audit rows and then saves the workbook.
The resume invariant is "audited implies replayable": a crash between
audit and save leaves rows the next resume re-writes from the audit,
with the true old values preserved in the pre-crash records. The
reverse order could not be healed for values derived from workbook
state — an appended note saved but not audited would be re-appended on
resume. `note_append` values are composed through
`routing.note_append_value`, which replays the audited prior instead
of appending a second copy. Re-applied *rejected* mutations do
re-audit: each refused attempt is its own event (asymmetric with
applied replays by design).

### Contract validation moved into the agent stage (amends guardrail 49.11)

Plan section 37 retries schema-validation failures, so the pydantic
contract check now runs inside `run_agent`, gating the retry loop.
Rule validation (deterministic checks) stays in the VALIDATE node and
is never retried. The raw output of the most recent attempt that
returned anything stays on disk either way.

### Fail-hard for scoping/fill; fail-soft for the review cycle

Section 37 says "after 2 retries → mark as UNRESOLVED, continue" —
but before WRITE_DRAFT there are no items to mark and "continuing"
would finalize an empty workbook. After exhausted retries:

- **CLAUDE_SCOPE / CLAUDE_FILL fail the run** (stage `failed`, run
  `failed`); the checkpoint survives, and `workflow resume` re-enters
  the stage with a fresh retry budget — the run is interrupted, not
  killed (user story 26's intent).
- **CODEX_REVIEW degrades**: no findings exist, and an empty review
  must not pass for all-clear, so every agent-written cell (from
  provenance) escalates straight to human review with both agents'
  columns empty.
- **CLAUDE_REVISE degrades** to zero decisions: the apply node runs an
  empty batch and every non-PASS finding becomes UNRESOLVED via the
  existing "no revision decision was returned" rule.
- **CODEX_REREVIEW degrades** to zero verdicts: a new general routing
  rule sends any REBUT without a verdict to UNRESOLVED ("rebuttal
  received no re-review verdict") — also closing the latent hole where
  an unadjudicated rebuttal could have passed silently.

### Failure classification vocabulary and audit shape

Transient classifications mirror section 37:
`runtime_process_failure` (AgentResult error), `invocation_failure`
(runtime raised), `schema_validation_failure` (contract violation).
Non-retryable stage exceptions record `deterministic`
(ValueError/MutationConflictError — pydantic ValidationError from
re-read artifacts is a ValueError subclass and lands here too) or
`unclassified` (environment errors such as a deleted answers file).
`stages` gained `retry_count` and `failure` columns: a degraded stage
is `completed` with `failure` set; a hard failure is `failed`; an
interrupted entry stays a dangling `started` row (ADR 0014). Each
retry also records a `stage_retry` event carrying the classification
that caused it, so recovered stages keep their failure history. The
run summary table renders both columns.

### Kills, run status, and resume

A kill (KeyboardInterrupt and other BaseExceptions) is never retried
and never classified — it propagates, the engine records the run as
`failed`, and the checkpoint survives. Non-terminal status transitions
(`running`, `paused`) clear `finished_at` stamped by an earlier
abnormal exit. Resuming a `completed` run is refused (it would
otherwise flip the terminal row back to `running` while executing
nothing). Crash-resume invokes the graph with no input (the documented
LangGraph form); a pending scoping interrupt — detected via
`get_state(config).interrupts` — resumes with `Command(resume=True)`
instead. LangGraph's own control-flow exceptions (GraphBubbleUp, i.e.
the interrupt) pass through the stage wrapper unrecorded.

### Kill-injection test idiom

The scripted runtime raises KeyboardInterrupt as the injectable
equivalent of a process kill at agent stages; kills inside the
deterministic mutating nodes are injected by wrapping
`writer.save_draft` (a public boundary of the writer layer), and the
mid-batch windows are additionally covered at the mutation layer's
unit seam (workbook-reset replay). Both integration paths compare the
resumed run against an uninterrupted baseline artifact-for-artifact.
