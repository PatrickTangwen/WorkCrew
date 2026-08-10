"""Review/revision routing rules (plan sections 27, 29, 30).

Pure deterministic review targeting and decision logic shared by the
graph's agent inputs, validators, conditional edges, and human-fallback
artifact generation. Source conflicts are protected for human review;
the section-27 behavior table binds which revision actions are legal for
the remaining findings. The module also derives the revision mutation
batch (plan sections 28, 37): decisions compose in order with
read-your-writes note composition and audited-prior replay (ADR 0021).
"""

from workflow_app.workbook import writer
from workflow_app.workbook.mutations import CellMutation
from workflow_app.workbook.safety import cell_key

ACTIONS_BY_VERDICT = {
    "WARN": {"ACCEPT", "REBUT"},
    "FAIL": {"FIX", "CLEAR", "UNRESOLVED"},
    "UNRESOLVED": {"FIX", "CLEAR", "UNRESOLVED"},
}


def _cell_identity(cell):
    """Canonicalize valid A1 addresses while preserving malformed values for errors."""
    return writer.normalize_cell(cell) or cell


def _duplicate_cell_identities(cells):
    seen = set()
    duplicates = []
    for cell in cells:
        identity = _cell_identity(cell)
        if identity in seen and identity not in duplicates:
            duplicates.append(identity)
        seen.add(identity)
    return duplicates


def plan_review_targets(extraction, schema, policy):
    """Return the deterministic cell ledger the Reviewer must cover."""
    field_order = {
        name: index for index, name in enumerate(schema.target_sheet().fields)
    }
    proposals_by_cell = {}
    for proposal in extraction.proposals:
        identity = _cell_identity(proposal.cell)
        if identity in proposals_by_cell:
            raise ValueError(
                f"extraction has duplicate proposals for cell {identity!r}"
            )
        proposals_by_cell[identity] = proposal
    proposals = sorted(
        proposals_by_cell.values(),
        key=lambda proposal: (
            proposal.row,
            field_order.get(proposal.column_name, len(field_order)),
            proposal.cell,
        ),
    )
    if policy.coverage == "full":
        return [
            {"cell": _cell_identity(proposal.cell), "reason": "full coverage"}
            for proposal in proposals
        ]

    reasons = {}

    def add_reason(proposal, reason):
        reasons.setdefault(_cell_identity(proposal.cell), []).append(reason)

    for proposal in proposals:
        if proposal.column_name in policy.strict_fields:
            add_reason(proposal, "strict field")
        if proposal.status == "proposed" and proposal.confidence in ("low", "medium"):
            add_reason(proposal, f"{proposal.confidence} confidence")
        if proposal.status in ("ambiguous", "conflict"):
            add_reason(proposal, f"{proposal.status} proposal")

    proposals_by_row = {}
    for proposal in proposals:
        proposals_by_row.setdefault(proposal.row, []).append(proposal)
    sample_count = policy.high_confidence_sampling_per_record
    field_count = len(field_order)
    for row_offset, row in enumerate(sorted(proposals_by_row)):
        if not sample_count or not field_count:
            continue
        start = row_offset * sample_count % field_count
        high_confidence = [
            proposal
            for proposal in proposals_by_row[row]
            if proposal.status == "proposed"
            and proposal.confidence == "high"
            and _cell_identity(proposal.cell) not in reasons
        ]
        high_confidence.sort(
            key=lambda proposal: (
                (field_order.get(proposal.column_name, field_count) - start)
                % field_count,
                proposal.cell,
            )
        )
        for proposal in high_confidence[:sample_count]:
            add_reason(proposal, "high-confidence rotation sample")

    return [
        {
            "cell": _cell_identity(proposal.cell),
            "reason": "; ".join(reasons[_cell_identity(proposal.cell)]),
        }
        for proposal in proposals
        if _cell_identity(proposal.cell) in reasons
    ]


def non_pass_findings(findings):
    return [finding for finding in findings if finding.verdict != "PASS"]


def route_revision_findings(findings, extraction):
    """Separate automatable findings from source conflicts reserved for people."""
    conflict_cells = {
        _cell_identity(proposal.cell)
        for proposal in extraction.proposals
        if proposal.status == "conflict"
    }
    actionable = non_pass_findings(findings)
    return {
        "agent_actionable": [
            finding
            for finding in actionable
            if _cell_identity(finding.cell) not in conflict_cells
        ],
        "human_only": [
            finding
            for finding in actionable
            if _cell_identity(finding.cell) in conflict_cells
        ],
    }


def check_decisions(findings, decisions):
    duplicates = _duplicate_cell_identities([decision.cell for decision in decisions])
    if duplicates:
        return f"revision returned duplicate decisions for cells: {duplicates}"

    by_cell = {_cell_identity(finding.cell): finding for finding in findings}
    for decision in decisions:
        finding = by_cell.get(_cell_identity(decision.cell))
        if finding is None:
            return f"decision for {decision.cell!r} has no matching finding"
        if finding.verdict == "PASS":
            return (
                f"decision for {decision.cell!r} targets a PASS finding;"
                " PASS cells are frozen"
            )
        allowed = ACTIONS_BY_VERDICT[finding.verdict]
        if decision.action not in allowed:
            return (
                f"action {decision.action!r} is not allowed for a"
                f" {finding.verdict} finding on {decision.cell!r}"
                f" (allowed: {sorted(allowed)})"
            )
        if decision.action == "ACCEPT" and finding.recommended_value is None:
            return (
                f"ACCEPT on {decision.cell!r} but the finding carries no"
                " recommended value"
            )
        if decision.note_append is not None and decision.action not in (
            "ACCEPT",
            "FIX",
            "CLEAR",
        ):
            return (
                f"note_append on {decision.cell!r} requires a primary edit"
                f" (ACCEPT/FIX/CLEAR), got {decision.action}"
            )
    return None


def rebutted_cells(decisions):
    return [
        _cell_identity(decision.cell)
        for decision in decisions
        if decision.action == "REBUT"
    ]


def check_re_review_coverage(rebutted, verdicts):
    rebutted = [_cell_identity(cell) for cell in rebutted]
    verdict_cells = [_cell_identity(verdict.cell) for verdict in verdicts]
    duplicates = _duplicate_cell_identities(verdict_cells)
    if duplicates:
        return f"re-review returned duplicate verdicts for cells: {duplicates}"
    missing = [cell for cell in rebutted if cell not in verdict_cells]
    if missing:
        return f"re-review returned no verdict for rebutted cells: {missing}"
    extra = [cell for cell in verdict_cells if cell not in rebutted]
    if extra:
        return f"re-review added verdicts for non-rebutted cells: {extra}"
    return None


def check_review_coverage(targets, findings):
    planned_cells = [_cell_identity(target["cell"]) for target in targets]
    finding_cells = [_cell_identity(finding.cell) for finding in findings]
    duplicates = _duplicate_cell_identities(finding_cells)
    if duplicates:
        return f"review returned duplicate findings for cells: {duplicates}"
    missing = [cell for cell in planned_cells if cell not in finding_cells]
    if missing:
        return f"review returned no finding for planned targets: {missing}"
    planned = set(planned_cells)
    extra = [
        _cell_identity(finding.cell)
        for finding in findings
        if _cell_identity(finding.cell) not in planned and not finding.missed_data
    ]
    if extra:
        return f"review added non-completeness findings outside the plan: {extra}"
    return None


def check_finding_cells(findings):
    for finding in findings:
        if writer.normalize_cell(finding.cell) is None:
            return f"finding has a malformed cell address {finding.cell!r}"
    return None


def note_append_value(current, note, prior):
    # Idempotent composition (plan section 37): a crash-resume re-runs
    # the apply node against a draft that already holds the appended
    # note; the audited prior value is replayed instead of appending a
    # second copy.
    if prior is not None:
        return prior["new_value"]
    return f"{current}\n{note}" if current else note


def compose_revision_mutations(
    decisions, findings, sheet_schema, read_current, find_prior
):
    # Values compose in decision order against the batch's own pending
    # writes: a note_append on a cell an earlier decision already wrote
    # — a previous note_append or a primary edit — composes on that
    # pending value, never on the stale batch-start read. `find_prior`
    # supplies the audited prior for idempotent replay (plan section
    # 37), which also seeds the pending value on a partial replay.
    duplicates = _duplicate_cell_identities([decision.cell for decision in decisions])
    if duplicates:
        raise ValueError(
            f"cannot compose duplicate revision decisions for cells: {duplicates}"
        )

    findings_by_cell = {_cell_identity(finding.cell): finding for finding in findings}
    mutations, decision_by_ref, pending = [], {}, {}
    for index, decision in enumerate(decisions):
        source_ref = f"decisions[{index}]"
        decision_by_ref[source_ref] = decision
        cell_ref = writer.normalize_cell(decision.cell)

        notes_ref = None
        if decision.note_append is not None:
            notes_ref = notes_cell_for(sheet_schema, cell_ref)
            if notes_ref is None:
                raise ValueError(
                    f"decision on {decision.cell!r} carries note_append but"
                    " the target sheet declares no notes_field"
                )

        if decision.action in ("ACCEPT", "FIX", "CLEAR"):
            if decision.action == "ACCEPT":
                value = findings_by_cell[
                    _cell_identity(decision.cell)
                ].recommended_value
            elif decision.action == "FIX":
                value = decision.proposed_value
            else:
                value = None
            if notes_ref == cell_ref:
                # The primary edit targets the Notes cell itself: the
                # note composes onto the new value inside the SAME
                # mutation — a second write under one idempotency key
                # would abort the whole batch (ADR 0021).
                prior = find_prior(cell_ref, source_ref)
                value = note_append_value(value, decision.note_append, prior)
                notes_ref = None
            mutations.append(
                CellMutation(
                    sheet=sheet_schema.name,
                    cell=decision.cell,
                    value=value,
                    actor_role="revision",
                    source_ref=source_ref,
                )
            )
            pending[cell_ref] = value

        if notes_ref is not None:
            if notes_ref in pending:
                current = pending[notes_ref]
            else:
                current = read_current(notes_ref)
            prior = find_prior(notes_ref, source_ref)
            text = note_append_value(current, decision.note_append, prior)
            mutations.append(
                CellMutation(
                    sheet=sheet_schema.name,
                    cell=notes_ref,
                    value=text,
                    actor_role="revision",
                    source_ref=source_ref,
                )
            )
            pending[notes_ref] = text
    return mutations, decision_by_ref


def notes_cell_for(sheet_schema, cell_ref):
    if sheet_schema.notes_field is None:
        return None
    notes_column = sheet_schema.fields[sheet_schema.notes_field].column
    return f"{notes_column}{writer.row_of(cell_ref)}"


def derive_revision_allowlist(findings, schema):
    # Flagged cells plus each flagged row's Notes cell, so note_append
    # companion edits are always authorized (plan section 28). PASS
    # cells never enter the list — they stay frozen.
    sheet = schema.target_sheet()
    cells = set()
    for finding in non_pass_findings(findings):
        cell_ref = writer.normalize_cell(finding.cell)
        cells.add(cell_key(sheet.name, cell_ref))
        notes_cell = notes_cell_for(sheet, cell_ref)
        if notes_cell is not None:
            cells.add(cell_key(sheet.name, notes_cell))
    return sorted(cells)


def collect_unresolved(findings, decisions, verdicts, human_only=()):
    decisions_by_cell = {
        _cell_identity(decision.cell): decision for decision in decisions
    }
    verdict_cells = {_cell_identity(verdict.cell) for verdict in verdicts}
    upheld = {
        _cell_identity(verdict.cell)
        for verdict in verdicts
        if verdict.verdict == "UPHELD"
    }
    human_only_cells = {_cell_identity(finding.cell) for finding in human_only}

    unresolved = []
    for finding in non_pass_findings(findings):
        identity = _cell_identity(finding.cell)
        if identity in human_only_cells:
            unresolved.append(
                {
                    "cell": identity,
                    "reason": "protected source conflict requires human review",
                }
            )
            continue
        decision = decisions_by_cell.get(identity)
        if decision is None:
            unresolved.append(
                {"cell": identity, "reason": "no revision decision was returned"}
            )
        elif decision.action == "UNRESOLVED":
            unresolved.append(
                {
                    "cell": identity,
                    "reason": "revision could not determine the correct action",
                }
            )
        elif decision.action == "REBUT" and identity in upheld:
            unresolved.append(
                {
                    "cell": identity,
                    "reason": "rebuttal upheld by the targeted re-review",
                }
            )
        elif decision.action == "REBUT" and identity not in verdict_cells:
            # A rebuttal that never received adjudication (the targeted
            # re-review did not complete) must not pass silently.
            unresolved.append(
                {
                    "cell": identity,
                    "reason": "rebuttal received no re-review verdict",
                }
            )
    return unresolved
