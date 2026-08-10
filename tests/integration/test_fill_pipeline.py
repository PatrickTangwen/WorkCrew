"""Fill-to-draft pipeline integration tests (ticket #5).

Primary seam: engine entry with a FakeAgentRuntime replaying a
realistic proposal distribution — applied cells, a medium-cap
violation, a vocabulary violation caught by the safety layer, and
not_found / ambiguous / conflict statuses. Assertions inspect artifacts
and the reopened draft workbook only.
"""

import json
from pathlib import Path

from openpyxl import load_workbook

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs

SHEET = "7) Practicum Courses"
BRIEF = "India 2008/Project_Brief.txt"


def evidence(text, evidence_type="direct"):
    return {
        "source_file": BRIEF,
        "source_location": "page 1",
        "evidence_text": text,
        "evidence_type": evidence_type,
    }


def proposal(row, column_name, cell, value, confidence, status="proposed", **extra):
    return {
        "sheet": SHEET,
        "row": row,
        "column_name": column_name,
        "cell": cell,
        "value": value,
        "evidence": [extra.pop("evidence", evidence("Stated in the brief."))],
        "rules_applied": extra.pop("rules_applied", []),
        "confidence": confidence,
        "status": status,
        **extra,
    }


FILLER_OUTPUT = {
    "proposals": [
        # Written: free-text field at high confidence.
        proposal(2, "Notes", "F2", "Community healthcare delivery.", "high"),
        # Written: vocabulary field below the cap, web-sourced evidence.
        proposal(
            2,
            "Main Issue Area(s)",
            "G2",
            "Healthcare",
            "medium",
            evidence=evidence("Program page names healthcare.", "external_web"),
        ),
        # Written: constructed ID below the cap.
        proposal(
            2,
            "Project ID*",
            "A2",
            "PRJ-0001",
            "medium",
            rules_applied=["PROJECT_ID_FORMAT"],
        ),
        # Validation-rejected: mapped field at the high threshold.
        proposal(2, "Maturity", "E2", "Established", "high"),
        # Safety-rejected: outside the controlled vocabulary.
        proposal(3, "Main Issue Area(s)", "G3", "Sorcery", "medium"),
        # Never written: uncertainty statuses.
        proposal(
            3,
            "Project ID*",
            "A3",
            None,
            None,
            status="not_found",
            notes="No project identifier was found.",
        ),
        proposal(
            3,
            "Maturity",
            "E3",
            None,
            None,
            status="ambiguous",
            notes="Emerging and established are both plausible.",
        ),
        proposal(
            4,
            "Notes",
            "F4",
            None,
            None,
            status="conflict",
            notes="Two sources disagree.",
        ),
        # Written, but low confidence: must surface for extra review.
        proposal(4, "Main Issue Area(s)", "G4", "Education", "low"),
    ]
}

APPLIED_CELLS = {
    "F2": "Community healthcare delivery.",
    "G2": "Healthcare",
    "A2": "PRJ-0001",
    "G4": "Education",
}
BLOCKED_CELLS = ["E2", "G3", "A3", "E3", "F4"]


REVIEW_OUTPUT = {
    "findings": [
        {
            "cell": cell,
            "verdict": "PASS",
            "evidence": [],
            "reviewer_comment": "Covered by the deterministic review plan.",
        }
        for cell in ("A2", "E2", "F2", "G2", "E3", "G3", "F4", "G4")
    ]
}


def start_run(inputs):
    fake = FakeAgentRuntime({"filler": FILLER_OUTPUT, "reviewer": REVIEW_OUTPUT})
    return run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            workbook_schema=inputs["workbook_schema"],
            scoping_answers=inputs["scoping_answers"],
        ),
        runs_root=inputs["runs_root"],
        runtimes={"filler": fake, "reviewer": fake},
    )


def artifacts(inputs, state):
    return Path(state["workspace_path"]) / "artifacts"


def test_declared_merges_flow_into_the_handoff(inputs):
    output = {
        "proposals": FILLER_OUTPUT["proposals"],
        "merges": [
            {
                "folders": ["India 2009"],
                "row": 2,
                "reason": "Duplicate of the 2008 folder.",
            }
        ],
    }
    fake = FakeAgentRuntime({"filler": output, "reviewer": REVIEW_OUTPUT})
    state = run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            workbook_schema=inputs["workbook_schema"],
            scoping_answers=inputs["scoping_answers"],
        ),
        runs_root=inputs["runs_root"],
        runtimes={"filler": fake, "reviewer": fake},
    )

    handoff = json.loads((artifacts(inputs, state) / "handoff.json").read_text())
    assert handoff["merges"] == output["merges"]
    text = (artifacts(inputs, state) / "handoff.md").read_text()
    assert "Duplicate of the 2008 folder." in text


def test_draft_contains_only_authorized_valid_proposals(inputs):
    state = start_run(inputs)

    draft_path = Path(state["draft_xlsx_path"])
    assert draft_path == Path(state["workspace_path"]) / "working/draft.xlsx"
    sheet = load_workbook(draft_path)[SHEET]

    for cell, value in APPLIED_CELLS.items():
        assert sheet[cell].value == value, cell
    for cell in BLOCKED_CELLS:
        assert sheet[cell].value is None, cell
    # Pre-existing content and formulas survive.
    assert sheet["A1"].value == "Project ID*"
    assert sheet["H2"].value == "=SUM(1,2)"


def test_validated_extraction_and_rejections_are_artifacts(inputs):
    state = start_run(inputs)

    extraction = json.loads((artifacts(inputs, state) / "extraction.json").read_text())
    assert len(extraction["proposals"]) == len(FILLER_OUTPUT["proposals"])

    validation = json.loads((artifacts(inputs, state) / "validation.json").read_text())
    (rejection,) = validation["rejections"]
    assert rejection["cell"] == f"{SHEET}!E2"
    assert "medium" in rejection["reason"]


def test_every_written_cell_has_a_full_provenance_record(inputs):
    state = start_run(inputs)

    provenance = json.loads((artifacts(inputs, state) / "provenance.json").read_text())
    entries = {entry["cell"]: entry for entry in provenance["entries"]}

    assert set(entries) == {f"{SHEET}!{cell}" for cell in APPLIED_CELLS}
    id_entry = entries[f"{SHEET}!A2"]
    assert id_entry["value"] == "PRJ-0001"
    assert id_entry["agent_role"] == "filler"
    assert id_entry["agent_runtime"] == "fake"
    assert id_entry["rules_applied"] == ["PROJECT_ID_FORMAT"]
    assert id_entry["confidence"] == "medium"
    assert id_entry["run_id"] == state["run_id"]
    (id_evidence,) = id_entry["evidence"]
    assert id_evidence["source_file"] == BRIEF
    assert id_evidence["source_location"] == "page 1"
    assert id_evidence["evidence_text"]
    assert id_evidence["evidence_type"] == "direct"
    # Web-sourced evidence keeps its tag (guardrail 49.6).
    web_entry = entries[f"{SHEET}!G2"]
    assert web_entry["evidence"][0]["evidence_type"] == "external_web"


def test_handoff_summarizes_the_fill(inputs):
    state = start_run(inputs)

    handoff = json.loads((artifacts(inputs, state) / "handoff.json").read_text())

    assert handoff["sources"]["total"] == 3
    (unreadable,) = handoff["sources"]["unreadable"]
    assert unreadable["path"] == "legacy_archive.zip"
    assert unreadable["status"] == "UNSUPPORTED"

    assert handoff["populated_cells"] == len(APPLIED_CELLS)
    assert handoff["records_evaluated"] == 3  # rows 2, 3, and 4
    assert handoff["confidence_distribution"] == {"low": 1, "medium": 3, "high": 2}
    assert handoff["evidence_summary"] == {"direct": 8, "external_web": 1}

    (missing,) = handoff["missing_fields"]
    assert missing["cell"] == f"{SHEET}!A3"
    assert missing["required"] is True

    (ambiguity,) = handoff["ambiguities"]
    assert ambiguity["cell"] == f"{SHEET}!E3"

    (conflict,) = handoff["source_conflicts"]
    assert conflict["cell"] == f"{SHEET}!F4"

    extra_review_cells = {item["cell"] for item in handoff["extra_review"]}
    assert extra_review_cells == {f"{SHEET}!E2", f"{SHEET}!G3", f"{SHEET}!G4"}


def test_handoff_markdown_is_rendered_for_humans(inputs):
    state = start_run(inputs)

    text = (artifacts(inputs, state) / "handoff.md").read_text()
    assert "legacy_archive.zip" in text
    assert "Confidence" in text
    assert f"{SHEET}!E2" in text
