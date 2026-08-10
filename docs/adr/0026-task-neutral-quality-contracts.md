# 0026 — Task-neutral quality contracts

Status: accepted
Date: 2026-08-09
Ticket: #14

## Context

The first full-coverage pilot exposed two forms of accidental coupling. A
proposal already marked `conflict` could leave the human-review queue when the
Reviewer returned `PASS` for its correctly blank workbook cell. Separately, an
active Reviewer prompt named one benchmark field instead of applying the local
rules supplied with any task.

The earlier source-conflict decision in ADR 0025 protected only non-PASS
findings. This record supersedes that narrower condition while preserving the
rest of ADR 0025.

Historical task prompts also contained useful workflow requirements: every
written value carried evidence, review did not mutate the workbook, PASS cells
were frozen, revision decisions were auditable, and handoff covered filled,
unfilled, uncertain, and human-only items. Those requirements should become
task-neutral contracts rather than copied domain instructions.

## Decisions

### Proposal status owns conflict escalation

Every extraction proposal with `status: conflict` is human-only regardless of
the Reviewer's verdict. It never enters Revision inputs or mutation allowlists
and always appears in unresolved and human-review artifacts. A Reviewer may
confirm that blank is the correct workbook representation, but cannot close the
underlying disagreement between sources.

This rule depends only on proposal status and canonical cell identity. It does
not inspect field names, source domains, benchmark labels, or expected values.

### Local rules own field semantics

Active quality prompts use the workbook schema and task-supplied rule files.
The Reviewer applies any canonical-form rule at its declared authority and
recommends an exact replacement only when the sources and rule determine it.
Core prompts do not name benchmark fields or encode benchmark answers.

### Machine artifacts own the handoff

The deterministic handoff contains one decision record per proposal: cell,
field, status, value, confidence, evidence source/location/type/text, applied
rules, and a substantive review note. Its Markdown rendering groups the same
ledger by sheet and row without dropping the evidence rationale. The structured
extraction remains authoritative; the handoff is a reconciled human-readable
index, not another agent judgment.

### Evidence gates claims and writes

A proposed value without source or rule evidence fails proposal validation and
cannot reach the workbook mutation layer. An explicit `not_found` search result
may carry no evidence when its notes record the search outcome.

A Revision decision that edits the workbook through `ACCEPT`, `FIX`, or `CLEAR`
is illegal without decision evidence. A `REBUT` is also illegal without
evidence because its disagreement with the Reviewer is a substantive claim.
PASS cells remain frozen, and non-editing unresolved decisions remain visible
for human adjudication.

## Consequences

False-positive conflict proposals now remain visible for human adjudication
instead of disappearing. Improving conflict precision belongs to the Filler;
routing must not hide it by selecting a value or silently finalizing a blank.

The same engine contracts are exercised against unrelated invoice and
application fixtures with different sheets, fields, and columns. These tests
demonstrate structural portability, but live quality across domains still
requires independent, label-withheld evaluation on representative tasks.
