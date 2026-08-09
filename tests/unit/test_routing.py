"""Review/revision routing rules (ticket #6, plan sections 27, 29, 30).

Pure decision logic: which findings are actionable, which decisions are
legal for which verdicts, which cells end up unresolved.
"""

import pytest

from workflow_app.models import ReReviewVerdict, ReviewFinding, RevisionDecision
from workflow_app.workflow.routing import (
    check_decisions,
    check_re_review_coverage,
    collect_unresolved,
    has_actionable_findings,
    rebutted_cells,
)


def finding(cell, verdict, recommended=None, comment="because"):
    return ReviewFinding.model_validate(
        {
            "cell": cell,
            "verdict": verdict,
            "recommended_value": recommended,
            "evidence": [],
            "reviewer_comment": comment,
        }
    )


def decision(cell, action, proposed=None, justification="reasoned"):
    return RevisionDecision.model_validate(
        {
            "cell": cell,
            "action": action,
            "proposed_value": proposed,
            "evidence": [],
            "justification": justification,
        }
    )


def verdict(cell, outcome):
    return ReReviewVerdict.model_validate(
        {"cell": cell, "verdict": outcome, "reviewer_comment": "adjudicated"}
    )


# --- actionability -------------------------------------------------------


def test_all_pass_is_not_actionable():
    assert not has_actionable_findings([finding("A2", "PASS"), finding("F2", "PASS")])


@pytest.mark.parametrize("bad", ["WARN", "FAIL", "UNRESOLVED"])
def test_any_non_pass_is_actionable(bad):
    assert has_actionable_findings([finding("A2", "PASS"), finding("F2", bad)])


# --- decision legality (plan section 27 behavior table) ------------------


def test_legal_decision_set_passes():
    findings = [
        finding("F2", "WARN", recommended="corrected"),
        finding("A2", "WARN", recommended="PRJ-0002"),
        finding("G4", "FAIL", recommended="Healthcare"),
        finding("D2", "UNRESOLVED"),
    ]
    decisions = [
        decision("F2", "ACCEPT"),
        decision("A2", "REBUT"),
        decision("G4", "CLEAR"),
        decision("D2", "UNRESOLVED"),
    ]
    assert check_decisions(findings, decisions) is None


def test_warn_must_be_accepted_or_rebutted():
    reason = check_decisions(
        [finding("F2", "WARN", recommended="x")], [decision("F2", "FIX", proposed="y")]
    )
    assert reason is not None and "WARN" in reason


def test_fail_may_not_be_rebutted():
    reason = check_decisions(
        [finding("G4", "FAIL", recommended="x")], [decision("G4", "REBUT")]
    )
    assert reason is not None and "FAIL" in reason


def test_accept_requires_a_recommended_value():
    reason = check_decisions([finding("F2", "WARN")], [decision("F2", "ACCEPT")])
    assert reason is not None and "recommended" in reason


def test_decision_for_unknown_cell_is_illegal():
    reason = check_decisions(
        [finding("F2", "WARN", recommended="x")], [decision("Z9", "ACCEPT")]
    )
    assert reason is not None and "Z9" in reason


def test_pass_cells_must_not_receive_decisions():
    reason = check_decisions([finding("G2", "PASS")], [decision("G2", "NO_CHANGE")])
    assert reason is not None and "PASS" in reason


def test_note_append_requires_a_primary_edit():
    rebut_with_note = RevisionDecision.model_validate(
        {
            "cell": "F2",
            "action": "REBUT",
            "note_append": "sneaky note on a disputed cell",
            "evidence": [],
            "justification": "disagree",
        }
    )
    reason = check_decisions(
        [finding("F2", "WARN", recommended="x")], [rebut_with_note]
    )
    assert reason is not None and "note_append" in reason


# --- rebuttals and re-review coverage ------------------------------------


def test_rebutted_cells_are_extracted_in_order():
    decisions = [
        decision("F2", "ACCEPT"),
        decision("A2", "REBUT"),
        decision("D2", "REBUT"),
    ]
    assert rebutted_cells(decisions) == ["A2", "D2"]


def test_re_review_must_cover_exactly_the_rebutted_cells():
    assert check_re_review_coverage(["A2"], [verdict("A2", "WITHDRAWN")]) is None

    missing = check_re_review_coverage(["A2", "D2"], [verdict("A2", "UPHELD")])
    assert missing is not None and "D2" in missing

    extra = check_re_review_coverage(
        ["A2"], [verdict("A2", "WITHDRAWN"), verdict("G2", "WITHDRAWN")]
    )
    assert extra is not None and "G2" in extra


# --- the unresolved set (plan section 29) --------------------------------


def test_unresolved_collects_all_three_sources():
    findings = [
        finding("F2", "WARN", recommended="x"),
        finding("A2", "WARN", recommended="y"),
        finding("D2", "WARN", recommended="z"),
        finding("G4", "FAIL", recommended="w"),
        finding("E3", "UNRESOLVED"),
    ]
    decisions = [
        decision("F2", "ACCEPT"),
        decision("A2", "REBUT"),  # withdrawn -> resolved
        decision("D2", "REBUT"),  # upheld -> unresolved
        decision("G4", "UNRESOLVED"),
        # E3 has no decision -> unresolved
    ]
    verdicts = [verdict("A2", "WITHDRAWN"), verdict("D2", "UPHELD")]

    unresolved = collect_unresolved(findings, decisions, verdicts)
    reasons = {item["cell"]: item["reason"] for item in unresolved}

    assert set(reasons) == {"D2", "G4", "E3"}
    assert "upheld" in reasons["D2"]
    assert "revision" in reasons["G4"]
    assert "no revision decision" in reasons["E3"]


def test_nothing_unresolved_when_all_closed():
    findings = [finding("F2", "WARN", recommended="x")]
    decisions = [decision("F2", "ACCEPT")]
    assert collect_unresolved(findings, decisions, []) == []
