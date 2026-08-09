"""Review -> revision -> re-review -> human-fallback routing (ticket #6).

Primary seam: engine entry with fakes for every role. The fixture
distribution exercises every route: PASS (frozen), WARN->ACCEPT,
WARN->REBUT->WITHDRAWN, FAIL->CLEAR with note_append, and
WARN->REBUT->UPHELD escalating to human review. Assertions inspect the
final workbook, artifacts, and audit only.
"""

import json
import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs

SHEET = "7) Practicum Courses"
BRIEF = "India 2008/Project_Brief.txt"

NOTE_TEXT = "Removed uncertain issue area Education; see review."


def evidence(text, evidence_type="direct"):
    return {
        "source_file": BRIEF,
        "source_location": "page 1",
        "evidence_text": text,
        "evidence_type": evidence_type,
    }


def proposal(row, column_name, cell, value, confidence):
    return {
        "sheet": SHEET,
        "row": row,
        "column_name": column_name,
        "cell": cell,
        "value": value,
        "evidence": [evidence("Stated in the brief.")],
        "rules_applied": [],
        "confidence": confidence,
        "status": "proposed",
    }


FILLER_OUTPUT = {
    "proposals": [
        proposal(2, "Notes", "F2", "First draft note.", 0.90),
        proposal(2, "Main Issue Area(s)", "G2", "Healthcare", 0.80),
        proposal(2, "Project ID*", "A2", "PRJ-0001", 0.70),
        proposal(2, "Start Date", "D2", "2026-01-01", 0.70),
        proposal(4, "Main Issue Area(s)", "G4", "Education", 0.70),
    ]
}


def finding(cell, verdict, recommended=None, comment="Reviewer comment."):
    return {
        "cell": cell,
        "verdict": verdict,
        "recommended_value": recommended,
        "evidence": [evidence("Checked against the annual report.")],
        "reviewer_comment": comment,
    }


REVIEW_OUTPUT = {
    "findings": [
        finding("G2", "PASS"),
        finding("F2", "WARN", recommended="Corrected community note."),
        finding("A2", "WARN", recommended="PRJ-0002"),
        finding("G4", "FAIL", recommended="Healthcare"),
        finding("D2", "WARN", recommended="2026-02-02"),
    ]
}


def decision(cell, action, proposed=None, note_append=None, justification="Because."):
    return {
        "cell": cell,
        "action": action,
        "proposed_value": proposed,
        "note_append": note_append,
        "evidence": [evidence("Re-checked the original brief.")],
        "justification": justification,
    }


REVISION_OUTPUT = {
    "decisions": [
        decision("F2", "ACCEPT"),
        decision("A2", "REBUT", justification="Brief explicitly names PRJ-0001."),
        decision(
            "G4",
            "CLEAR",
            note_append=NOTE_TEXT,
            justification="Issue area cannot be determined from sources.",
        ),
        decision("D2", "REBUT", justification="Program page confirms the date."),
    ]
}

RE_REVIEW_OUTPUT = {
    "verdicts": [
        {"cell": "A2", "verdict": "WITHDRAWN", "reviewer_comment": "Convinced."},
        {"cell": "D2", "verdict": "UPHELD", "reviewer_comment": "Evidence stands."},
    ]
}


def start_run(inputs, review=None, runtimes=None):
    outputs = {
        "filler": FILLER_OUTPUT,
        "reviewer": review or REVIEW_OUTPUT,
        "revision": REVISION_OUTPUT,
        "re_review": RE_REVIEW_OUTPUT,
    }
    if runtimes is None:
        runtimes = {role: FakeAgentRuntime(outputs) for role in outputs}
    return run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            workbook_schema=inputs["workbook_schema"],
        ),
        runs_root=inputs["runs_root"],
        runtimes=runtimes,
    )


def workspace_of(state):
    return Path(state["workspace_path"])


def read_artifact(state, name):
    return json.loads((workspace_of(state) / "artifacts" / name).read_text())


def stage_names(state):
    with sqlite3.connect(workspace_of(state) / "state/audit.sqlite") as conn:
        rows = conn.execute(
            "SELECT stage FROM stages WHERE run_id = ? ORDER BY id",
            (state["run_id"],),
        ).fetchall()
    return [row[0] for row in rows]


def test_final_workbook_reflects_every_route(inputs):
    state = start_run(inputs)

    final = workspace_of(state) / "output/final.xlsx"
    assert Path(state["draft_xlsx_path"]).read_bytes() == final.read_bytes()
    sheet = load_workbook(final)[SHEET]

    assert sheet["F2"].value == "Corrected community note."  # ACCEPT
    assert sheet["G2"].value == "Healthcare"  # PASS frozen
    assert sheet["A2"].value == "PRJ-0001"  # REBUT withdrawn, original kept
    assert sheet["G4"].value is None  # CLEAR
    assert sheet["F4"].value == NOTE_TEXT  # note_append companion
    assert sheet["D2"].value == "2026-01-01"  # upheld rebuttal, no change
    assert sheet["H2"].value == "=SUM(1,2)"  # untouched formula


def test_pass_cells_receive_no_revision_mutations(inputs):
    state = start_run(inputs)

    with sqlite3.connect(workspace_of(state) / "state/audit.sqlite") as conn:
        rows = conn.execute(
            "SELECT cell FROM mutations WHERE actor_role = 'revision'"
            " AND status = 'applied'"
        ).fetchall()
    assert {row[0] for row in rows} == {"F2", "G4", "F4"}


def test_revision_receives_only_the_allowed_context(inputs):
    state = start_run(inputs)

    revision_inputs = json.loads(
        (workspace_of(state) / "agent_outputs/revision/inputs.json").read_text()
    )

    finding_cells = {item["cell"] for item in revision_inputs["findings"]}
    assert finding_cells == {"F2", "A2", "G4", "D2"}  # no PASS finding

    assert set(revision_inputs["proposals"]) == {"F2", "A2", "G4", "D2"}
    assert set(revision_inputs["provenance"]) == {"F2", "A2", "G4", "D2"}

    assert revision_inputs["mutation_allowlist"] == sorted(
        [
            f"{SHEET}!F2",
            f"{SHEET}!A2",
            f"{SHEET}!G4",
            f"{SHEET}!D2",
            f"{SHEET}!F4",  # Notes companion of flagged row 4
        ]
    )


def test_exactly_one_re_review_over_rebutted_cells_only(inputs):
    state = start_run(inputs)

    assert stage_names(state).count("CODEX_REREVIEW") == 1
    re_review = read_artifact(state, "re_review.json")
    assert {v["cell"] for v in re_review["verdicts"]} == {"A2", "D2"}


def test_unresolved_and_human_review_artifacts(inputs):
    state = start_run(inputs)

    unresolved = read_artifact(state, "unresolved.json")
    (item,) = unresolved["cells"]
    assert item["cell"] == "D2"
    assert "upheld" in item["reason"]

    human = read_artifact(state, "human_review.json")
    (entry,) = human["items"]
    assert entry["cell"] == "D2"
    assert entry["current_value"] == "2026-01-01"
    assert entry["reviewer"]["recommended_value"] == "2026-02-02"
    assert entry["reviewer"]["comment"]
    assert entry["revision"]["action"] == "REBUT"
    assert entry["revision"]["justification"]
    assert entry["re_review"]["verdict"] == "UPHELD"
    assert "upheld" in entry["reason"]

    text = (workspace_of(state) / "artifacts/human_review.md").read_text()
    assert "D2" in text and "2026-02-02" in text


def test_provenance_stays_in_sync_with_revised_cells(inputs):
    state = start_run(inputs)

    provenance = read_artifact(state, "provenance.json")
    entries = {entry["cell"]: entry for entry in provenance["entries"]}

    accept = entries[f"{SHEET}!F2"]
    assert accept["value"] == "Corrected community note."
    assert accept["agent_role"] == "revision"

    cleared = entries[f"{SHEET}!G4"]
    assert cleared["value"] is None
    assert cleared["agent_role"] == "revision"

    note = entries[f"{SHEET}!F4"]
    assert note["value"] == NOTE_TEXT
    assert note["agent_role"] == "revision"

    untouched = entries[f"{SHEET}!A2"]
    assert untouched["value"] == "PRJ-0001"
    assert untouched["agent_role"] == "filler"


def test_review_artifacts_are_produced(inputs):
    state = start_run(inputs)

    review = read_artifact(state, "review.json")
    assert len(review["findings"]) == 5
    assert Path(state["review_path"]).name == "review.json"

    revision = read_artifact(state, "revision.json")
    assert len(revision["decisions"]) == 4

    for name in ("review.md", "revision_log.md"):
        assert (workspace_of(state) / "artifacts" / name).read_text()


def test_all_pass_review_short_circuits_to_finalize(inputs):
    all_pass = {"findings": [finding(cell, "PASS") for cell in ("F2", "G2")]}
    # Only filler and reviewer runtimes exist: reaching revision or
    # re-review would raise KeyError inside the fake.
    runtimes = {
        "filler": FakeAgentRuntime({"filler": FILLER_OUTPUT}),
        "reviewer": FakeAgentRuntime({"reviewer": all_pass}),
    }
    state = start_run(inputs, review=all_pass, runtimes=runtimes)

    stages = stage_names(state)
    for absent in (
        "CLAUDE_REVISE",
        "APPLY_ALLOWED_REVISIONS",
        "CODEX_REREVIEW",
        "HUMAN_REVIEW",
    ):
        assert absent not in stages

    final = load_workbook(workspace_of(state) / "output/final.xlsx")[SHEET]
    assert final["F2"].value == "First draft note."


def test_illegal_decision_fails_the_run(inputs):
    bad_revision = {
        "decisions": [
            decision("F2", "FIX", proposed="sneaky fix")
        ]  # WARN needs ACCEPT/REBUT
    }
    outputs = {
        "filler": FILLER_OUTPUT,
        "reviewer": REVIEW_OUTPUT,
        "revision": bad_revision,
        "re_review": RE_REVIEW_OUTPUT,
    }
    runtimes = {role: FakeAgentRuntime(outputs) for role in outputs}
    with pytest.raises(ValueError, match="WARN"):
        start_run(inputs, runtimes=runtimes)
