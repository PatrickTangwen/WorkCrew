# 0021 — Same-batch note composition reads pending writes

Status: accepted (amends 0011/0016's note_append composition)
Date: 2026-08-09
Ticket: none (pre-existing bug found by #9's review, deferred there)

## Context

`APPLY_ALLOWED_REVISIONS` composed every `note_append` against the
draft workbook as read at batch start. Two decisions in one revision
batch appending to the same Notes cell — two flagged cells on the same
row, a common shape in real datasets — each composed against the same
stale read, so the second write clobbered the first and only the last
note survived. The same stale-read composition also broke the
mid-audit crash window: a resume whose first note replays from the
audit composed the second note against the unaudited (empty) workbook
value.

## Decision

### Composition is read-your-writes within the batch

Mutation values are now derived by
`routing.compose_revision_mutations`, which walks the decisions in
order and tracks the batch's pending value per cell. A `note_append`
composes against, in precedence order:

1. the audited prior for its own (cell, source_ref) key — idempotent
   replay, unchanged from ADR 0016;
2. the pending value an earlier decision in the same batch produced
   for that cell — a previous `note_append` or a primary edit
   (ACCEPT/FIX/CLEAR) targeting the Notes cell itself;
3. the draft workbook value, only when the batch has not yet written
   the cell.

Every composed value (including replayed priors) updates the pending
map, so a partial replay — first note audited, crash, resume — seeds
the pending value from the audit and the unaudited second note
composes correctly on top of it.

### Ordering semantics are positional and last-write-wins

Appends compose; primary edits are absolute writes. A primary edit to
the Notes cell that comes *after* an append in the same batch
overwrites the composed notes — decision order is the authority, and
the layer applies it faithfully rather than reordering or merging.

### Self-targeting decisions compose into one mutation (added 2026-08-09)

A single decision whose primary edit targets the Notes cell itself
*and* that carries its own `note_append` used to emit two mutations
with different values under one (cell, source_ref) idempotency key,
so the mutation layer raised MutationConflictError and aborted the
batch — permanently, since a resume replays the same decisions file
into the same conflict. The combination is legal per `check_decisions`
and actively steered into by the revision prompt (CLEAR MUST carry a
note_append), so a FAIL finding on a Notes cell made the abort
deterministic. Resolution: the pair composes into ONE mutation — the
note appends onto the new primary value (for CLEAR, the note alone
survives, preserving the cleared cell's context). Replay follows the
same audited-prior rule as every other composition.

### The composition seam lives in routing

The derivation moved from an inline loop in the graph's apply node
into `routing.compose_revision_mutations(decisions, findings,
sheet_schema, read_current, find_prior)` with the workbook read and
audit lookup injected, making the batch semantics (and the crash
windows) unit-testable without a workbook or audit store. The mutation
layer is unchanged: it still receives concrete values and enforces
ADR 0011/0016 idempotency and conflict rules.
