"""Review/revision routing rules (plan sections 27, 29, 30).

Pure deterministic decision logic shared by the graph's conditional
edges and the human-fallback artifact generation. Only non-PASS
findings are actionable; the section-27 behavior table binds which
revision actions are legal per verdict; the unresolved set feeds human
review.
"""

from workflow_app.workbook import writer
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
