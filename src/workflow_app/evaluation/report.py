"""Evaluation report artifact (ticket #13, plan section 42).

evaluation.json is the machine-readable record (and the shape recorded
as a baseline); evaluation.md is the human summary — the metric table
with numerators/denominators, then every labeled cell that missed its
expected final state.
"""

METRIC_NOTES = {
    "field_accuracy": "expected-value cells whose final value matches",
    "missed_data_rate": "expected-value cells left blank",
    "unsupported_fill_rate": "expected-blank cells that got filled",
    "provenance_coverage": "filled labeled cells with evidence from their row's folder",
    "review_true_positive_rate": "wrong draft cells the review flagged",
    "review_false_positive_rate": "correct draft cells the review flagged",
    "revision_correctness": "primary-edit decisions whose cell ended correct",
    "unresolved_count": "cells escalated to human review",
    "expected_unresolved_escalated": "known-conflict cells that were escalated",
    "web_evidence_percentage": "evidence entries sourced from the web",
}


def format_metric(metric):
    if not isinstance(metric, dict):
        return str(metric), ""
    value = "n/a" if metric["value"] is None else f"{metric['value']:.1%}"
    return value, f"{metric['numerator']} / {metric['denominator']}"


def _runtime_line(run):
    duration = run["duration_seconds"]
    rendered = "n/a" if duration is None else f"{duration:.0f}s"
    return f"- Runtime: {rendered} across {len(run['stages'])} stages"


def render_evaluation_md(evaluation):
    lines = [
        f"# Evaluation - {evaluation['benchmark']}",
        "",
        f"- Run: `{evaluation['run_id']}`",
        f"- Sheet: {evaluation['sheet']}",
        f"- Labeled cells: {len(evaluation['cells'])}",
        _runtime_line(evaluation["run"]),
        "",
        "| Metric | Value | n / d | Meaning |",
        "| --- | --- | --- | --- |",
    ]
    for name, metric in evaluation["metrics"].items():
        value, detail = format_metric(metric)
        lines.append(f"| {name} | {value} | {detail} | {METRIC_NOTES[name]} |")

    misses = [cell for cell in evaluation["cells"] if not cell["final_correct"]]
    if misses:
        lines += [
            "",
            "## Misses",
            "",
            "| Cell | Field | Status | Expected | Draft | Final | Flagged | Escalated |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for cell in misses:
            lines.append(
                "| {cell} | {field} | {status} | {expected_value} |"
                " {draft_value} | {final_value} | {flagged} | {escalated} |".format(
                    **cell
                )
            )
    else:
        lines += ["", "Every labeled cell reached its expected final state."]
    return "\n".join(lines) + "\n"
