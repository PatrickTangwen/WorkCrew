# 0027 — Proposal-complete and final review explorers

Status: accepted
Date: 2026-08-10
Ticket: #14

## Context

ADR 0015 defined the review explorer as a workbook-and-provenance view. That
was sufficient when the explorer's job was to show cells actually written by
the Filler or Revision. The task-neutral quality contract in ADR 0026 made
non-written proposal outcomes equally important: `not_found`, `ambiguous`, and
`conflict` are decisions with evidence and review direction, and a source
conflict remains human-only even when its workbook cell is correctly blank.

The old row-discovery rule could omit a row whose proposals were all blank,
because neither the workbook nor applied-mutation provenance referenced it.
The old v2 was also generated immediately after Revision, before re-review and
human-review routing, so it could not be a final audit view.

This record supersedes ADR 0015's row-discovery rule and its decision that v2
has no revision-annotation layer. The remaining ADR 0015 decisions stay in
force.

## Decisions

### V1 is the fill-time decision view

V1 continues to be generated immediately after the draft is written. Its row
set is the union of workbook rows, provenance rows, and rows named by handoff
decision records. Each schema field may carry its Filler proposal status,
value, confidence, complete typed evidence, applied rules, and review
direction. Proposal evidence also supplies folder membership for blank rows.
Malformed or schema-mismatched rejected proposals remain in overview findings
but are not projected as workbook rows or fields.

The current workbook value and applied-mutation provenance remain distinct
from the proposal. This distinction lets a rejected or uncertain proposal stay
visible without pretending that it was written.

### V2 is the final review-cycle view

Every successfully completed run generates bilingual v2 explorers during
`FINALIZE`, after Reviewer, Revision, re-review, and human-review routing have
finished. V2 re-renders the final draft and current provenance, then overlays
the structured review-cycle artifacts:

- Reviewer verdict, recommendation, comment, and evidence;
- Revision action, proposed value, note append, justification, and evidence;
- re-review verdict and comment; and
- final unresolved reason.

The overview derives verdict, action, re-review, and unresolved counts from
those artifacts. A run with no revisions still receives v2 because PASS is an
audited outcome, not the absence of a review cycle.

### The explorer remains task-neutral and deterministic

Status and action enums drive badges and summaries. Workbook fields, source
domains, benchmark labels, expected answers, and instance-specific counts do
not affect rendering. EN and ZH remain two renderings of one language-neutral
data model; UI labels are localized while workbook values, rules, comments,
and evidence excerpts remain unchanged.

The explorer performs no agent judgment. It projects existing machine
artifacts and escapes embedded data using the existing single-file HTML safety
contract.

## Consequences

Blank conflicts and entirely blank proposal rows are navigable and auditable.
V1 preserves the original fill snapshot, while v2 becomes the authoritative
human-facing summary of the completed automated review cycle. The underlying
JSON artifacts remain authoritative when a consumer needs machine processing.

Completed runs now always contain both V1 and V2 explorer pairs. Runs that fail
before `FINALIZE` may contain V1 only, which truthfully reflects the furthest
completed stage.
