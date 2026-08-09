"""Review/revision routing rules (plan sections 27, 29, 30).

Pure deterministic decision logic shared by the graph's conditional
edges and the human-fallback artifact generation. Only non-PASS
findings are actionable; the section-27 behavior table binds which
revision actions are legal per verdict; the unresolved set feeds human
review.
"""

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


def collect_unresolved(findings, decisions, verdicts):
    decisions_by_cell = {decision.cell: decision for decision in decisions}
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
    return unresolved
