# 0012 — Fill-pipeline artifacts and semantics

Status: accepted
Date: 2026-08-08
Ticket: #5 (fill-to-draft pipeline)

## Decisions

### `handoff.py` is a top-level module; `validation.json` is a new artifact

Plan section 34 assigns handoff generation no home (it is neither
provenance rendering nor a role contract), so it joins the recorded
top-level additions of ADR 0009. `artifacts/validation.json` records
per-proposal rejections (index, cell, reason) from the VALIDATE node;
plan section 35 does not list it, but rejections must be machine-
readable for the handoff, the audit trail, and later routing.

### Confidence thresholds are hardcoded V1 constants

Plan section 25 shows thresholds inside the review-policy YAML; the
frozen decision "V1 rule engine: HARDCODED" (section 44) wins for the
validation layer. The values are the spec's (low < 0.60 <= medium
< 0.85 <= high), named LOW/HIGH_CONFIDENCE_THRESHOLD after the buckets
they separate. The #6 review policy may make review *sampling* depths
configurable without moving the cap.

### The fill allowlist derives from the validated proposals

For the fill pass, the binding write gates are proposal validation and
schema writability plus the value checks inside the safety layer; the
allowlist is generated from the proposals that survived validation, so
its authorization step is structural rather than restrictive here.
Section 28's restrictive allowlist semantics (flagged cells only, Notes
companions) arrive with the revision pass in #6.

### Confidence distribution covers all proposed proposals

The handoff distribution reports the Filler's self-declared confidence
across every status="proposed" proposal — including ones validation or
the safety layer later rejected — because it describes the Filler's
output, not the write outcome. Written-cell confidence is recoverable
from provenance.json.
