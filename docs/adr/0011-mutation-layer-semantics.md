# 0011 — Mutation-layer semantics

Status: accepted
Date: 2026-08-08
Ticket: #4 (deterministic workbook safety layer)

## Decisions

### Idempotency key is (cell, actor role, source proposal), not cell alone

Plan section 37 words the check as "has this cell already been written
in this run?". Keyed on the cell alone, Revision could never correct a
cell the Filler wrote. The key is refined to
(sheet, cell, actor_role, source_ref): identical replays skip without
side effects (crash-resume safe, in the same batch or across runs);
the same source resubmitting a *different* value raises
MutationConflictError and aborts the whole batch before any save or
audit; a different actor/source may legitimately rewrite the cell, and
the audit trail records both writes with their old values.

### Actor gating is enforced at the API, not just by routing

Guardrails 49.8/49.9 (Reviewer never mutates; Revision never gets
unrestricted access) are structural — routing never hands the Reviewer
a mutation path. The mutation API additionally rejects any actor
outside {filler, revision}, so the guarantee holds even if a future
caller misroutes.

### Plan-section-17 rule classes are split across layers

The mutation layer runs type, controlled-vocabulary, ID-pattern, and
date-format checks. Required-field validation is a proposal-level
completeness concern and lands with the #5 validation pipeline. A None
value always passes value checks (clearing is type-safe); CLEAR
authorization semantics arrive with #6.

### Section-14 "Pydantic validation" happens upstream

CellMutation is a plain dataclass. The Pydantic step of the section-14
chain validates agent output (CellProposal et al.) in the #5 pipeline
before mutations are derived; this layer owns rule validation,
authorization, idempotency, and the write itself.

### Formula protection is the writable flag plus formula-preserving IO

ADR 0010 deferred section-16 "formulas / existing values" capture to
this ticket. Resolution: formula columns are simply not declared
writable (schema-level), and the writer loads with formulas preserved
(openpyxl data_only=False), so untouched cells — values and formulas —
survive save/reopen unchanged. No separate formula field is needed.
