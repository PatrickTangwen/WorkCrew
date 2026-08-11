# ADR 0030: Exception-only V2 field audit

Date: 2026-08-10

Status: the `filled` exclusion below is superseded by ADR 0034; the
exception-only principle stands.

## Context

ADR 0029 introduced a compact V2 review layer while retaining the complete
decision audit in the generated HTML. In practice, a field that was filled in
V1 and passed through the review workflow unchanged is an ordinary final
field, not a review exception. Giving that field an audit capsule and a
row-level audit panel obscures the final workbook view and overstates the
importance of a no-op review decision.

The underlying audit data must remain durable, and the presentation rule must
stay independent of benchmark-specific fields, values, or expected answers.

## Decision

V2 renders decision-audit UI only for fields whose structured workflow result
is one of these review exceptions:

- `revised`: the final non-empty value differs from the pre-revision value;
- `cleared`: a previously non-empty value was cleared; or
- `rebutted`: Revision recorded a structured `REBUT` action and kept the value.

Fields classified as `filled`, and fields with no net change, render only the
final value and current provenance. They receive no change capsule, compact
decision note, decision-audit panel, or row-level audit toggle.

The proposal, Reviewer, Revision, applied-change, re-review, and unresolved
records remain in the embedded data and durable JSON artifacts. V2 search only
matches decision-audit metadata for fields whose audit UI can be rendered, so
a search cannot select a row because of hidden ordinary-field metadata. V1
continues to expose fill-time proposal and review details as before.

Eligibility is derived solely from the generic structured change kind and
Revision action. It does not inspect dataset names, field names, values,
folders, or benchmark answers.

## Consequences

The V2 row detail remains a clean final-workbook view for ordinary filled and
unchanged fields. Revised, cleared, and rebutted fields retain the compact
exception marker and complete on-demand audit needed for review. Auditability
is preserved at the data layer without making every reviewed field visually
exceptional.
