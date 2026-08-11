# ADR 0034: V2 audit covers every applied change

Date: 2026-08-10

Supersedes the `filled` exclusion in ADR 0030.

## Context

ADR 0030 restricted V2 decision-audit UI to `revised`, `cleared`, and
`rebutted` fields on the grounds that a field "filled in V1 and passed
through the review workflow unchanged" is an ordinary final field. That
reasoning is sound, but the `filled` change kind does not describe it: a
`filled` cell was empty in V1 and the Revision wrote a value into it, which
is an applied workflow change. Excluding it left the overview reporting a
non-zero `filled` count with no field in any row marked as its cause, so a
reviewer could not locate the changed cells.

The established `practicum_courses_review_v2.html` marks exactly this case
with a `FILLED · QA` tag, and its overview indexes the cell changes,
rebuttals, and unresolved items so each exception is one click away.

## Decision

The V2 exception rule is stated in terms of what the workflow did to the
cell, not in terms of a kind list:

- A field the workflow left exactly as the Filler wrote it renders only its
  final value and current provenance — no change capsule, compact note,
  decision-audit panel, or row-level audit toggle.
- A field with an applied net change (`filled`, `revised`, or `cleared`) or
  a structured `REBUT` decision renders the compact localized badge, the
  Revision justification, and the on-demand decision audit of ADR 0029.
- A `filled` note omits the before/after line: there is no prior value to
  contrast, and the after value is the final value shown directly above it.
- A cell cleared by the revision reads as cleared rather than as an ordinary
  blank.

The overview `QA review & v2 revision (date)` section keeps its four net
counts and adds three collapsed indexes — cell changes, rebuttals, and
unresolved items — each row naming the sheet row and field and navigating to
that row's detail. Row and field identity come from the embedded data, so the
index stays consistent with the field-level rule by construction.

Eligibility still derives solely from the generic structured change kind and
Revision action. It does not inspect dataset names, field names, values,
folders, or benchmark answers.

## Consequences

Every count the overview reports is now reachable: no applied change is
invisible at the field level, and no unchanged field is dressed as an
exception. The clean final-workbook reading of ordinary rows is preserved,
and the durable JSON artifacts remain the complete audit record.
