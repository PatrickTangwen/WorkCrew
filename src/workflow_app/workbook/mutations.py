"""Deterministic workbook mutation API (plan sections 14, 28, 36, 37).

The only code path allowed to touch the workbook. Each mutation is
checked in the plan-section-14 order — value validation, then
authorization — plus the per-run idempotency check of section 37,
before openpyxl writes anything. Idempotency covers both earlier runs
(via the audit store) and earlier mutations in the same batch. Every
first-time applied or rejected mutation is audited; an idempotent
replay (same key, same value) writes the value again — a crash-resume
may have reset the workbook — but adds no audit record, so downstream
consumers see the same outcomes as an uninterrupted run. The audit
records land BEFORE the workbook save: a crash in between leaves
audited-but-unsaved writes that the next resume replays from the audit
(the invariant a resume relies on is "audited implies replayable",
which a save-first order cannot provide for values derived from
workbook state, e.g. note appends). Re-applied *rejected* mutations do
re-audit — each refused attempt is its own event. A
MutationConflictError aborts the whole batch before any save or audit
— no partial application.

Only the Filler and Revision roles may mutate the workbook (guardrails
49.8/49.9); the routing layer never hands other roles a mutation path,
and this boundary enforces it structurally as well.
"""

from dataclasses import dataclass
from typing import Any, Literal

from workflow_app.rules.deterministic import check_value
from workflow_app.workbook import writer

ALLOWED_ACTORS = frozenset({"filler", "revision"})


@dataclass(frozen=True)
class CellMutation:
    sheet: str
    cell: str
    value: Any
    actor_role: str
    source_ref: str


@dataclass(frozen=True)
class MutationOutcome:
    mutation: CellMutation
    status: Literal["applied", "rejected"]
    reason: str | None = None
    old_value: Any = None
    # Normalized A1 address; None only when the address was malformed.
    cell_ref: str | None = None
    # True when this application re-ran an already-audited write.
    replayed: bool = False


class MutationConflictError(Exception):
    """Same run, cell, actor, and source proposal — but a different value."""


def apply_mutations(draft_path, mutations, schema, allowlist, audit, run_id):
    workbook = writer.open_draft(draft_path)
    written = {}  # in-batch idempotency: (sheet, cell, actor, source) -> value
    outcomes = [
        _apply_one(workbook, mutation, schema, allowlist, audit, run_id, written)
        for mutation in mutations
    ]

    # Audit before the save: a crash between the two leaves audited
    # writes the next resume replays onto a fresh workbook, with the
    # true old values preserved in the pre-crash records. Replays leave
    # no new applied trail.
    for outcome in outcomes:
        if not outcome.replayed:
            audit.record_mutation(run_id, _record(outcome))

    if any(outcome.status == "applied" for outcome in outcomes):
        writer.save_draft(workbook, draft_path)
    return outcomes


def _apply_one(workbook, mutation, schema, allowlist, audit, run_id, written):
    def rejected(reason, cell_ref=None):
        return MutationOutcome(
            mutation=mutation, status="rejected", reason=reason, cell_ref=cell_ref
        )

    if mutation.actor_role not in ALLOWED_ACTORS:
        return rejected(f"actor {mutation.actor_role!r} may not mutate the workbook")

    cell_ref = writer.normalize_cell(mutation.cell)
    if cell_ref is None:
        return rejected(f"malformed cell address {mutation.cell!r}")

    if not writer.has_sheet(workbook, mutation.sheet):
        return rejected(
            f"sheet {mutation.sheet!r} is not present in the workbook", cell_ref
        )

    sheet_schema = schema.sheet_named(mutation.sheet)
    if sheet_schema is None:
        return rejected(
            f"sheet {mutation.sheet!r} is not described by the workbook schema",
            cell_ref,
        )

    column = writer.column_of(cell_ref)
    header, field = sheet_schema.field_for_column(column)
    if field is None:
        return rejected(f"no field declared for column {column}", cell_ref)

    if not field.writable:
        return rejected(f"column {column} ({header}) is not writable", cell_ref)

    reason = check_value(field, mutation.value)
    if reason is not None:
        return rejected(reason, cell_ref)

    if not allowlist.permits(mutation.sheet, cell_ref):
        return rejected(
            f"cell {mutation.sheet}!{cell_ref} is not in the allowlist", cell_ref
        )

    key = (mutation.sheet, cell_ref, mutation.actor_role, mutation.source_ref)
    prior = _prior_value(key, written, audit, run_id)
    if prior is not None and prior["new_value"] != mutation.value:
        raise MutationConflictError(
            f"{mutation.sheet}!{cell_ref} was already written as"
            f" {prior['new_value']!r} by {mutation.actor_role}/"
            f"{mutation.source_ref}; refusing to replay it as"
            f" {mutation.value!r}"
        )

    old_value = writer.read_cell(workbook, mutation.sheet, cell_ref)
    writer.write_cell(workbook, mutation.sheet, cell_ref, mutation.value)
    written[key] = mutation.value
    return MutationOutcome(
        mutation=mutation,
        status="applied",
        old_value=old_value,
        cell_ref=cell_ref,
        replayed=prior is not None,
    )


def _prior_value(key, written, audit, run_id):
    if key in written:
        return {"new_value": written[key]}
    sheet, cell_ref, actor_role, source_ref = key
    return audit.find_applied_mutation(run_id, sheet, cell_ref, actor_role, source_ref)


def _record(outcome):
    mutation = outcome.mutation
    # Malformed addresses are audited verbatim, exactly as requested.
    cell = outcome.cell_ref if outcome.cell_ref is not None else mutation.cell
    return {
        "sheet": mutation.sheet,
        "cell": cell,
        "old_value": outcome.old_value,
        "new_value": mutation.value,
        "actor_role": mutation.actor_role,
        "source_ref": mutation.source_ref,
        "status": outcome.status,
        "reason": outcome.reason,
    }
