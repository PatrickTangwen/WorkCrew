# ADR 0029: Compact V2 review explorer

Date: 2026-08-10

## Context

ADR 0027 made the proposal, current workbook, Reviewer, Revision, re-review,
and unresolved layers available in the final explorer. Displaying every layer
as an always-open card made ordinary row inspection substantially denser than
the established `practicum_courses_review_v2.html` experience.

The V2 explorer still needs to preserve its task-neutral audit contract. It
must not use benchmark field names, expected values, or domain-specific action
labels to decide what changed.

## Decision

V2 keeps the existing overview and row-detail structure, with a compact review
layer modeled on the established explorer:

- The overview adds one `QA review & v2 revision (date)` section. The date is
  derived from the durable run timeline, and the four chips are the generic net
  `filled`, `revised`, `cleared`, and structured `rebutted` counts defined by
  ADR 0028.
- A normal field shows its final workbook value and current provenance.
- A field with an applied net change shows a compact localized change badge,
  before/after values, and the Revision justification when available.
- A structured `REBUT` decision shows a compact retained/rebutted badge and its
  justification even though it does not mutate the workbook.
- Proposal, Reviewer, Revision, applied-change, re-review, and unresolved
  details remain present in the V2 HTML under the row-level `Decision audit`
  toggle. A search hit inside those details opens them automatically.
- V1 presentation remains unchanged: proposal metadata continues to be shown
  directly because V1 is the fill-time review artifact.

The presentation logic depends only on the structured review-cycle contract
and applied mutation audit. It does not inspect dataset-specific fields,
folders, labels, values, or benchmark answers.

## Consequences

The default V2 experience is close to the earlier explorer while the complete
audit remains locally inspectable. Cleared cells and rebutted decisions remain
discoverable as first-class field rows. The compact summary intentionally does
not repeat the lower-level verdict, action, and re-review count groups; those
details remain in the decision audit and JSON artifacts.
