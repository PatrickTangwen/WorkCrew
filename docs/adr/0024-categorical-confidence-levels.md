# 0024 — Categorical confidence levels

Status: accepted
Date: 2026-08-09
Ticket: #14 (quality iteration)

## Decision

Filler proposals use the ordinal confidence levels `low`, `medium`, and
`high`, not numeric self-scores. Confidence is required only when
`status="proposed"`; `not_found`, `ambiguous`, and `conflict` proposals carry
`confidence: null` because their status already expresses why no value can be
supported. Constructed and mapped fields remain capped at `medium`.

Reviewer policy routes these levels directly: low-confidence proposals receive
full verification, medium-confidence proposals receive priority, and only
high-confidence proposals use per-record spot sampling. Numeric threshold
configuration is removed. Provenance preserves the categorical level for
Filler writes and continues to record null for Revision writes.

## Rationale

The former 0.0–1.0 values were uncalibrated LLM self-assessments that the
engine immediately converted into three fixed buckets. Keeping the apparent
precision added configuration and audit complexity without evidence that, for
example, 0.82 was meaningfully different from 0.80. Categories make the
agent contract, review routing, and human interpretation share one vocabulary.

## Consequences

This decision supersedes the numeric confidence sections of ADR 0012 and the
numeric review thresholds in ADR 0018. It is intentionally a breaking
contract: extraction artifacts and review-policy YAML containing numeric
confidence values or thresholds fail validation instead of being silently
converted. Historical run artifacts and recorded baselines remain historical
evidence; new runs use the categorical contract, while attempts to resume an
older numeric run fail fast.
