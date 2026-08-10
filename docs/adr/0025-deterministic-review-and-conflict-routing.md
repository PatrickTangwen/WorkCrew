# 0025 — Deterministic review coverage and protected conflict routing

Status: accepted
Date: 2026-08-09
Ticket: #14 (quality against the Kleister baseline)

## Context

The independent-prompt full benchmark showed two engine-level gaps. The
Reviewer saw only a policy and chose its own coverage, so 32 of 48 wrong draft
cells were never reviewed. Separately, six extraction proposals already marked
as source conflicts reached Revision, where legal `CLEAR` and `FIX` decisions
removed every one from the human-review queue.

## Decisions

### The routing module owns the review target ledger

`workflow/routing.py` plans Reviewer targets from the validated extraction,
workbook schema, and review policy. `coverage: full` includes every proposal.
The backward-compatible default, `coverage: sampled`, includes every strict
field, low- or medium-confidence proposal, ambiguous or conflicting proposal,
and a configured number of remaining high-confidence proposals per row. High
confidence sampling rotates through stable schema order across rows.

The graph records this ledger in the Reviewer inputs. Reviewer output must
contain every planned cell exactly once. Duplicate findings fail validation.
A finding outside the ledger is legal only when `missed_data` is true, which
preserves the separate completeness sweep without returning coverage selection
to the agent.

### Source conflicts are not Revision actions

A non-PASS finding whose matching extraction proposal has `status: conflict`
is `human_only`. It bypasses Revision inputs and the mutation allowlist and
enters human review with the reason `protected source conflict requires human
review`. All other non-PASS findings remain `agent_actionable` under the action
table in ADR 0013.

The graph validates Revision decisions only against `agent_actionable`
findings. A guessed decision for a protected conflict therefore fails as an
unknown finding instead of being silently converted to `UNRESOLVED`. When a
review contains only protected conflicts, the graph skips Revision entirely.

## Consequences

Review coverage and conflict action legality are deterministic engine
invariants, while source verification and completeness discovery remain agent
judgments. Existing review-policy YAML keeps sampled behavior. Quality pilots
may opt into `coverage: full` explicitly and must record that configuration
when comparing results with earlier runs.
