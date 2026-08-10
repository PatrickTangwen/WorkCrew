"""Review/revision routing rules (ticket #6, plan sections 27, 29, 30).

Pure decision logic: which findings are actionable, which decisions are
legal for which verdicts, which cells end up unresolved.
"""

import pytest

from workflow_app.models import (
    CellProposal,
    ExtractionResult,
    ReReviewVerdict,
    ReviewFinding,
    RevisionDecision,
)
from workflow_app.review_policy import ReviewPolicy
from workflow_app.workbook.schema import SheetSchema, WorkbookSchema
from workflow_app.workflow.routing import (
    check_decisions,
    check_re_review_coverage,
    check_review_coverage,
    collect_unresolved,
    compose_revision_mutations,
    note_append_value,
    plan_review_targets,
    rebutted_cells,
    route_revision_findings,
)


def finding(cell, verdict, recommended=None, comment="because", missed_data=False):
    return ReviewFinding.model_validate(
        {
            "cell": cell,
            "verdict": verdict,
            "recommended_value": recommended,
            "evidence": [],
            "reviewer_comment": comment,
            "missed_data": missed_data,
        }
    )


def decision(cell, action, proposed=None, note_append=None, justification="reasoned"):
    return RevisionDecision.model_validate(
        {
            "cell": cell,
            "action": action,
            "proposed_value": proposed,
            "note_append": note_append,
            "evidence": [],
            "justification": justification,
        }
    )


def verdict(cell, outcome):
    return ReReviewVerdict.model_validate(
        {"cell": cell, "verdict": outcome, "reviewer_comment": "adjudicated"}
    )


def proposal(cell, status="proposed", column_name="Field", confidence=None):
    return CellProposal.model_validate(
        {
            "sheet": "Sheet",
            "row": int(cell[1:]),
            "column_name": column_name,
            "cell": cell,
            "value": "value" if status == "proposed" else None,
            "evidence": [],
            "rules_applied": [],
            "confidence": (confidence or "high") if status == "proposed" else None,
            "status": status,
        }
    )


REVIEW_SCHEMA = WorkbookSchema.model_validate(
    {
        "sheets": [
            {
                "name": "Sheet",
                "target": True,
                "fields": {
                    "Alpha": {"column": "A", "writable": True},
                    "Beta": {"column": "B", "writable": True},
                    "Gamma": {"column": "C", "writable": True},
                    "Delta": {"column": "D", "writable": True},
                },
            }
        ]
    }
)


# --- actionability -------------------------------------------------------


def test_source_conflicts_are_human_only_revision_findings():
    findings = [
        finding("H5", "UNRESOLVED"),
        finding("J5", "FAIL", recommended="Small"),
        finding("G5", "FAIL", recommended="AB1 2CD"),
    ]
    extraction = ExtractionResult(
        proposals=[
            proposal("H5", "conflict"),
            proposal("J5", "conflict"),
            proposal("G5", "ambiguous"),
        ]
    )

    routed = route_revision_findings(findings, extraction)

    assert [item.cell for item in routed["agent_actionable"]] == ["G5"]
    assert [item.cell for item in routed["human_only"]] == ["H5", "J5"]
    assert (
        check_decisions(routed["agent_actionable"], [decision("G5", "UNRESOLVED")])
        is None
    )


# --- deterministic review coverage --------------------------------------


def test_full_review_targets_every_proposal_in_stable_schema_order():
    extraction = ExtractionResult(
        proposals=[
            proposal("B3", column_name="Beta"),
            proposal("C2", "conflict", column_name="Gamma"),
            proposal("A3", column_name="Alpha"),
            proposal("B2", column_name="Beta", confidence="medium"),
            proposal("A2", "not_found", column_name="Alpha"),
        ]
    )

    targets = plan_review_targets(
        extraction, REVIEW_SCHEMA, ReviewPolicy(coverage="full")
    )

    assert targets == [
        {"cell": "A2", "reason": "full coverage"},
        {"cell": "B2", "reason": "full coverage"},
        {"cell": "C2", "reason": "full coverage"},
        {"cell": "A3", "reason": "full coverage"},
        {"cell": "B3", "reason": "full coverage"},
    ]


def test_review_target_plan_rejects_duplicate_proposal_cells():
    extraction = ExtractionResult(
        proposals=[
            proposal("A2", column_name="Alpha"),
            proposal("A2", column_name="Alpha"),
        ]
    )

    with pytest.raises(ValueError, match="duplicate.*A2"):
        plan_review_targets(extraction, REVIEW_SCHEMA, ReviewPolicy())


def test_sampled_review_targets_mandatory_cells_and_rotates_high_confidence():
    extraction = ExtractionResult(
        proposals=[
            proposal("D3", "conflict", column_name="Delta"),
            proposal("A3", column_name="Alpha"),
            proposal("C2", column_name="Gamma", confidence="low"),
            proposal("D2", "not_found", column_name="Delta"),
            proposal("B3", column_name="Beta"),
            proposal("A2", column_name="Alpha"),
            proposal("C3", "ambiguous", column_name="Gamma"),
            proposal("B2", column_name="Beta", confidence="medium"),
        ]
    )
    policy = ReviewPolicy(
        coverage="sampled",
        strict_fields=["Delta"],
        high_confidence_sampling_per_record=1,
    )

    targets = plan_review_targets(extraction, REVIEW_SCHEMA, policy)

    assert targets == [
        {"cell": "A2", "reason": "high-confidence rotation sample"},
        {"cell": "B2", "reason": "medium confidence"},
        {"cell": "C2", "reason": "low confidence"},
        {"cell": "D2", "reason": "strict field"},
        {"cell": "B3", "reason": "high-confidence rotation sample"},
        {"cell": "C3", "reason": "ambiguous proposal"},
        {"cell": "D3", "reason": "strict field; conflict proposal"},
    ]


def test_review_coverage_rejects_a_missing_planned_target():
    targets = [
        {"cell": "A2", "reason": "full coverage"},
        {"cell": "B2", "reason": "full coverage"},
    ]

    reason = check_review_coverage(targets, [finding("A2", "PASS")])

    assert reason is not None and "B2" in reason


def test_review_coverage_rejects_duplicate_findings():
    targets = [{"cell": "A2", "reason": "full coverage"}]

    reason = check_review_coverage(
        targets, [finding("A2", "PASS"), finding("A2", "WARN")]
    )

    assert reason is not None and "duplicate" in reason and "A2" in reason


def test_review_coverage_allows_extra_findings_only_for_missed_data():
    targets = [{"cell": "A2", "reason": "full coverage"}]
    planned = finding("A2", "PASS")

    illegal = check_review_coverage(targets, [planned, finding("B2", "FAIL")])
    allowed = check_review_coverage(
        targets, [planned, finding("B2", "FAIL", missed_data=True)]
    )

    assert illegal is not None and "B2" in illegal
    assert allowed is None


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


def test_protected_source_conflicts_have_an_explicit_human_reason():
    conflict = finding("H5", "UNRESOLVED")

    unresolved = collect_unresolved([conflict], [], [], human_only=[conflict])

    assert unresolved == [
        {
            "cell": "H5",
            "reason": "protected source conflict requires human review",
        }
    ]


def test_nothing_unresolved_when_all_closed():
    findings = [finding("F2", "WARN", recommended="x")]
    decisions = [decision("F2", "ACCEPT")]
    assert collect_unresolved(findings, decisions, []) == []


def test_rebuttal_without_any_verdict_is_unresolved():
    unresolved = collect_unresolved(
        [finding("A2", "WARN", recommended="x")],
        [decision("A2", "REBUT")],
        [],
    )
    assert unresolved == [
        {"cell": "A2", "reason": "rebuttal received no re-review verdict"}
    ]


# --- revision mutation composition (same-batch note appends) -------------


SHEET_SCHEMA = SheetSchema.model_validate(
    {
        "name": "Sheet",
        "notes_field": "Notes",
        "fields": {
            "Start Date": {"type": "date", "column": "D", "writable": True},
            "Notes": {"type": "string", "column": "F", "writable": True},
            "Issue": {"type": "string", "column": "G", "writable": True},
        },
    }
)


def compose(decisions, findings, current=None, priors=None):
    return compose_revision_mutations(
        decisions,
        findings,
        SHEET_SCHEMA,
        lambda ref: (current or {}).get(ref),
        lambda ref, source_ref: (priors or {}).get((ref, source_ref)),
    )


def test_same_batch_note_appends_compose_cumulatively():
    findings = [finding("G4", "FAIL"), finding("D4", "FAIL")]
    decisions = [
        decision("G4", "CLEAR", note_append="note one"),
        decision("D4", "FIX", proposed="2026-04-04", note_append="note two"),
    ]

    mutations, by_ref = compose(decisions, findings)

    assert [(m.cell, m.value) for m in mutations] == [
        ("G4", None),
        ("F4", "note one"),
        ("D4", "2026-04-04"),
        ("F4", "note one\nnote two"),
    ]
    assert by_ref == {"decisions[0]": decisions[0], "decisions[1]": decisions[1]}


def test_first_note_append_composes_on_the_workbook_value():
    mutations, _ = compose(
        [decision("G4", "CLEAR", note_append="note one")],
        [finding("G4", "FAIL")],
        current={"F4": "existing note"},
    )
    assert [(m.cell, m.value) for m in mutations] == [
        ("G4", None),
        ("F4", "existing note\nnote one"),
    ]


def test_replay_composes_both_notes_from_the_audited_priors():
    # Crash after audit, before save: the workbook reads stale, but
    # each audited prior replays verbatim, second note included.
    findings = [finding("G4", "FAIL"), finding("D4", "FAIL")]
    decisions = [
        decision("G4", "CLEAR", note_append="note one"),
        decision("D4", "FIX", proposed="2026-04-04", note_append="note two"),
    ]
    priors = {
        ("F4", "decisions[0]"): {"new_value": "note one"},
        ("F4", "decisions[1]"): {"new_value": "note one\nnote two"},
    }

    mutations, _ = compose(decisions, findings, priors=priors)

    assert [m.value for m in mutations if m.cell == "F4"] == [
        "note one",
        "note one\nnote two",
    ]


def test_partial_replay_composes_the_unaudited_note_on_the_replayed_prior():
    # Crash in the middle of the audit loop: only the first note was
    # audited and nothing was saved. The second note must compose on
    # the first's replayed value, not on the stale workbook read.
    findings = [finding("G4", "FAIL"), finding("D4", "FAIL")]
    decisions = [
        decision("G4", "CLEAR", note_append="note one"),
        decision("D4", "FIX", proposed="2026-04-04", note_append="note two"),
    ]
    priors = {("F4", "decisions[0]"): {"new_value": "note one"}}

    mutations, _ = compose(decisions, findings, priors=priors)

    assert [m.value for m in mutations if m.cell == "F4"] == [
        "note one",
        "note one\nnote two",
    ]


def test_note_append_composes_onto_a_same_batch_primary_edit():
    # An earlier decision replaces the Notes cell itself; a later
    # note_append in the same batch appends to the replacement, not to
    # the stale batch-start value.
    findings = [
        finding("F4", "WARN", recommended="Replacement note."),
        finding("D4", "FAIL"),
    ]
    decisions = [
        decision("F4", "ACCEPT"),
        decision("D4", "FIX", proposed="2026-04-04", note_append="companion"),
    ]

    mutations, _ = compose(decisions, findings, current={"F4": "stale original"})

    assert [m.value for m in mutations if m.cell == "F4"] == [
        "Replacement note.",
        "Replacement note.\ncompanion",
    ]


def test_a_later_primary_edit_to_the_notes_cell_overwrites_composed_notes():
    # Decision order is the authority (ADR 0021): a primary edit is an
    # absolute write, so coming after an append it wins.
    findings = [
        finding("G4", "FAIL"),
        finding("F4", "WARN", recommended="Full rewrite."),
    ]
    decisions = [
        decision("G4", "CLEAR", note_append="note one"),
        decision("F4", "ACCEPT"),
    ]

    mutations, _ = compose(decisions, findings)

    assert [m.value for m in mutations if m.cell == "F4"] == [
        "note one",
        "Full rewrite.",
    ]


def test_self_targeting_note_append_composes_into_one_mutation():
    # A primary edit on the Notes cell itself carrying its own note:
    # one mutation with the note composed onto the new value — a second
    # write under the same idempotency key would abort the batch.
    findings = [finding("F4", "FAIL")]
    decisions = [
        decision("F4", "FIX", proposed="Rewritten note.", note_append="context")
    ]

    mutations, _ = compose(decisions, findings, current={"F4": "stale original"})

    assert [(m.cell, m.value, m.source_ref) for m in mutations] == [
        ("F4", "Rewritten note.\ncontext", "decisions[0]")
    ]


def test_self_targeting_clear_keeps_only_the_note():
    # CLEAR on the Notes cell + note: the note alone survives.
    findings = [finding("F4", "FAIL")]
    decisions = [decision("F4", "CLEAR", note_append="why it was cleared")]

    mutations, _ = compose(decisions, findings, current={"F4": "old notes"})

    assert [(m.cell, m.value) for m in mutations] == [("F4", "why it was cleared")]


def test_self_targeting_note_replays_the_audited_prior():
    findings = [finding("F4", "FAIL")]
    decisions = [
        decision("F4", "FIX", proposed="Rewritten note.", note_append="context")
    ]
    priors = {("F4", "decisions[0]"): {"new_value": "Rewritten note.\ncontext"}}

    mutations, _ = compose(decisions, findings, priors=priors)

    assert [(m.cell, m.value) for m in mutations] == [
        ("F4", "Rewritten note.\ncontext")
    ]


def test_companion_append_composes_onto_a_self_targeting_edit():
    # A later decision's companion note lands on top of the merged
    # self-target write, under its own idempotency key.
    findings = [finding("F4", "FAIL"), finding("D4", "FAIL")]
    decisions = [
        decision("F4", "FIX", proposed="Rewritten note.", note_append="one"),
        decision("D4", "FIX", proposed="2026-04-04", note_append="two"),
    ]

    mutations, _ = compose(decisions, findings)

    assert [(m.cell, m.value, m.source_ref) for m in mutations if m.cell == "F4"] == [
        ("F4", "Rewritten note.\none", "decisions[0]"),
        ("F4", "Rewritten note.\none\ntwo", "decisions[1]"),
    ]


def test_note_append_without_a_notes_field_is_refused():
    bare = SheetSchema.model_validate(
        {"name": "Sheet", "fields": {"Issue": {"column": "G", "writable": True}}}
    )
    with pytest.raises(ValueError, match="notes_field"):
        compose_revision_mutations(
            [decision("G4", "CLEAR", note_append="note")],
            [finding("G4", "FAIL")],
            bare,
            lambda ref: None,
            lambda ref, source_ref: None,
        )


def test_note_append_value_replays_the_audited_prior():
    assert note_append_value("old", "note", {"new_value": "old\nnote"}) == "old\nnote"


def test_note_append_value_appends_to_existing_text():
    assert note_append_value("old", "note", None) == "old\nnote"


def test_note_append_value_starts_an_empty_notes_cell():
    assert note_append_value(None, "note", None) == "note"
