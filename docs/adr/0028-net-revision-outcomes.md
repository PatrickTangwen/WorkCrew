# 0028 — Net revision outcomes in the final explorer

Status: accepted
Date: 2026-08-10
Ticket: #14 follow-up

## Context

The original Practicum Courses v2 explorer summarized its manual QA cycle as
fixed, revised, cleared, and rebutted counts. ADR 0015 deliberately removed
that instance-specific panel when the explorer became workbook-neutral. ADR
0027 later restored a structured final review-cycle view, but its Revision
action counts still describe intent rather than effect: `FIX` can fill a blank
or replace a value, while a `CLEAR` with a same-cell note append can finish
nonblank.

The generalized explorer therefore needs the useful old summary without
reintroducing workbook fields, benchmark answers, or hand-authored counts.

## Decision

V2 derives one net outcome per target-sheet cell from the durable audit trail
of applied Revision mutations. Mutations stay in audit order and are collapsed
by cell: the first `old_value` is the before value and the final `new_value` is
the after value. Multiple companion writes to one Notes cell therefore count
once. A net-unchanged cell does not count.

The classifications are value-based:

- `filled`: null to non-null;
- `cleared`: non-null to null; and
- `revised`: two unequal non-null values.

`rebutted` counts unique structured `REBUT` decision cells. It is deliberately
decision-based because a rebuttal authorizes no workbook mutation. Later
re-review can withdraw or uphold it without changing the fact that Revision
made a rebuttal.

The final EN/ZH explorers show all four counts in a Revision outcomes group.
Fields with an applied net change also show its localized classification and
before/after values. Existing Reviewer verdict, Revision action, re-review,
and unresolved summaries remain visible as the lower-level audit view. V1 has
no revision outcome layer.

## Consequences

Outcome counts can legitimately differ from action counts. This is expected:
the former report actual cell effects, while the latter report agent decisions.
The values come from the mutation audit rather than inferred action semantics,
so crash-resume, companion-note composition, scalar types, and arbitrary
workbook schemas share one deterministic algorithm.

The explorer data model gains `review_cycle.change_counts` and an optional
per-field `revision_change`. No source domain, field name, benchmark label,
expected answer, or instance-specific total participates in the derivation.
