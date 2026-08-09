"""Review/revision routing rules (plan sections 27, 29, 30).

Pure deterministic decision logic shared by the graph's conditional
edges and the human-fallback artifact generation. Only non-PASS
findings are actionable; the section-27 behavior table binds which
revision actions are legal per verdict; the unresolved set feeds human
review. The module also derives the revision mutation batch (plan
sections 28, 37): decisions compose in order with read-your-writes
note composition and audited-prior replay (ADR 0021).
"""

from workflow_app.workbook import writer
from workflow_app.workbook.mutations import CellMutation
from workflow_app.workbook.safety import cell_key

ACTIONS_BY_VERDICT = {
    "WARN": {"ACCEPT", "REBUT"},
    "FAIL": {"FIX", "CLEAR", "UNRESOLVED"},
    "UNRESOLVED": {"FIX", "CLEAR", "UNRESOLVED"},
}


def non_pass_findings(findings):
    return [finding for finding in findings if finding.verdict != "PASS"]


def has_actionable_findings(findings):
    return bool(non_pass_findings(findings))


def check_decisions(findings, decisions):
    by_cell = {finding.cell: finding for finding in findings}
    for decision in decisions:
        finding = by_cell.get(decision.cell)
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
    return [decision.cell for decision in decisions if decision.action == "REBUT"]


def check_re_review_coverage(rebutted, verdicts):
    verdict_cells = [verdict.cell for verdict in verdicts]
    missing = [cell for cell in rebutted if cell not in verdict_cells]
    if missing:
        return f"re-review returned no verdict for rebutted cells: {missing}"
    extra = [cell for cell in verdict_cells if cell not in rebutted]
    if extra:
        return f"re-review added verdicts for non-rebutted cells: {extra}"
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
    findings_by_cell = {finding.cell: finding for finding in findings}
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
                value = findings_by_cell[decision.cell].recommended_value
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


def collect_unresolved(findings, decisions, verdicts):
    decisions_by_cell = {decision.cell: decision for decision in decisions}
    verdict_cells = {verdict.cell for verdict in verdicts}
    upheld = {verdict.cell for verdict in verdicts if verdict.verdict == "UPHELD"}

    unresolved = []
    for finding in non_pass_findings(findings):
        decision = decisions_by_cell.get(finding.cell)
        if decision is None:
            unresolved.append(
                {"cell": finding.cell, "reason": "no revision decision was returned"}
            )
        elif decision.action == "UNRESOLVED":
            unresolved.append(
                {
                    "cell": finding.cell,
                    "reason": "revision could not determine the correct action",
                }
            )
        elif decision.action == "REBUT" and finding.cell in upheld:
            unresolved.append(
                {
                    "cell": finding.cell,
                    "reason": "rebuttal upheld by the targeted re-review",
                }
            )
        elif decision.action == "REBUT" and finding.cell not in verdict_cells:
            # A rebuttal that never received adjudication (the targeted
            # re-review did not complete) must not pass silently.
            unresolved.append(
                {
                    "cell": finding.cell,
                    "reason": "rebuttal received no re-review verdict",
                }
            )
    return unresolved
