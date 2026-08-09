"""Review explorer integration tests (ticket #8, plan sections 22, 35).

Seam: the engine entry with fakes injected; assertions inspect the
generated explorer artifacts. The embedded data blob is extracted and
parsed to verify content consistency with the workbook and provenance.
"""

import json
import re
from pathlib import Path

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs

CONTRACT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"

V1_FILES = ("review_explorer.html", "review_explorer_zh.html")
V2_FILES = ("review_explorer_v2.html", "review_explorer_zh_v2.html")


SHEET = "7) Practicum Courses"
BRIEF = "India 2008/Project_Brief.txt"

REVISED_NOTE = "Corrected community note."

FILLER_OUTPUT = {
    "proposals": [
        {
            "sheet": SHEET,
            "row": 2,
            "column_name": column_name,
            "cell": cell,
            "value": value,
            "evidence": [
                {
                    "source_file": BRIEF,
                    "source_location": "page 1",
                    "evidence_text": "Stated in the brief.",
                    "evidence_type": "direct",
                }
            ],
            "rules_applied": [],
            # Constructed fields cap at medium confidence (ADR 0024).
            "confidence": "medium" if column_name == "Project ID*" else "high",
            "status": "proposed",
        }
        for column_name, cell, value in (
            ("Project ID*", "A2", "PRJ-0001"),
            ("Notes", "F2", "First draft note."),
        )
    ]
}

REVIEW_OUTPUT = {
    "findings": [
        {
            "cell": "F2",
            "verdict": "WARN",
            "recommended_value": REVISED_NOTE,
            "evidence": [
                {
                    "source_file": BRIEF,
                    "source_location": "page 2",
                    "evidence_text": "The report names the community.",
                    "evidence_type": "direct",
                }
            ],
            "reviewer_comment": "Note misses the community name.",
        }
    ]
}

REVISION_OUTPUT = {
    "decisions": [
        {
            "cell": "F2",
            "action": "ACCEPT",
            "proposed_value": None,
            "note_append": None,
            "evidence": [
                {
                    "source_file": BRIEF,
                    "source_location": "page 2",
                    "evidence_text": "Re-checked the original brief.",
                    "evidence_type": "direct",
                }
            ],
            "justification": "Reviewer evidence is stronger.",
        }
    ]
}


def filler_fixture():
    proposal = json.loads((CONTRACT_FIXTURES / "cell_proposal.json").read_text())
    return {"proposals": [proposal]}


def start_run(inputs, filler=None, review=None, revision=None):
    outputs = {
        "filler": filler or filler_fixture(),
        "reviewer": review or {"findings": []},
    }
    if revision is not None:
        outputs["revision"] = revision
    fake = FakeAgentRuntime(outputs)
    return run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            workbook_schema=inputs["workbook_schema"],
            scoping_answers=inputs["scoping_answers"],
        ),
        runs_root=inputs["runs_root"],
        runtimes={role: fake for role in outputs},
    )


def artifacts_dir(inputs, state):
    return inputs["runs_root"] / state["run_id"] / "artifacts"


def embedded_data(html):
    match = re.search(r"const DATA = (.*);$", html, re.MULTILINE)
    assert match, "explorer HTML must embed its data as `const DATA = ...;`"
    return json.loads(match.group(1))


def field_value(data, row_number, name, key="value"):
    (row,) = [row for row in data["rows"] if row["row"] == row_number]
    (field,) = [field for field in row["fields"] if field["name"] == name]
    return field[key]


def assert_selfcontained(html):
    assert "<html" in html
    # Single self-contained file: no external resource references.
    for marker in (
        'src="http',
        'href="http',
        'src="//',
        'href="//',
        "@import",
        "<link",
        "url(",
    ):
        assert marker not in html


def test_run_generates_selfcontained_bilingual_v1_explorers(inputs):
    state = start_run(inputs)
    artifacts = artifacts_dir(inputs, state)

    for name in V1_FILES:
        html = (artifacts / name).read_text()
        assert_selfcontained(html)
        data = embedded_data(html)
        # Handoff attention items surface as overview findings — the
        # fixture's unreadable archive must be one of them.
        assert {
            "kind": "unreadable_source",
            "ref": "legacy_archive.zip",
            "detail": "UNSUPPORTED",
        } in data["findings"]


def test_straight_through_run_has_no_v2_explorers(inputs):
    state = start_run(inputs)
    artifacts = artifacts_dir(inputs, state)

    for name in V2_FILES:
        assert not (artifacts / name).exists()


def test_v2_explorers_match_revised_workbook_and_provenance(inputs):
    state = start_run(
        inputs,
        filler=FILLER_OUTPUT,
        review=REVIEW_OUTPUT,
        revision=REVISION_OUTPUT,
    )
    artifacts = artifacts_dir(inputs, state)

    v1 = embedded_data((artifacts / "review_explorer.html").read_text())
    v2 = embedded_data((artifacts / "review_explorer_v2.html").read_text())

    # v1 keeps the fill-time state; v2 shows the revised cell.
    assert field_value(v1, 2, "Notes") == "First draft note."
    assert field_value(v2, 2, "Notes") == REVISED_NOTE
    assert field_value(v1, 2, "Notes", "role") == "filler"
    assert field_value(v2, 2, "Notes", "role") == "revision"
    assert [source["text"] for source in field_value(v2, 2, "Notes", "sources")] == [
        "Re-checked the original brief."
    ]
    # The untouched cell is identical in both versions.
    assert field_value(v2, 2, "Project ID*") == "PRJ-0001"

    # v2 matches the final workbook exactly.
    from openpyxl import load_workbook

    final = load_workbook(inputs["runs_root"] / state["run_id"] / "output/final.xlsx")
    sheet = final[SHEET]
    for row in v2["rows"]:
        for field in row["fields"]:
            if field["column"] is None:
                continue
            cell_value = sheet[f"{field['column']}{row['row']}"].value
            expected = cell_value if cell_value is None else str(cell_value)
            actual = field["value"] if field["value"] is None else str(field["value"])
            assert actual == expected

    # v2 matches the updated provenance exactly: every entry appears
    # on its field with matching author role and evidence.
    provenance = json.loads((artifacts / "provenance.json").read_text())
    assert provenance["entries"], "fixture must produce provenance"
    fields_by_cell = {
        f"{field['column']}{row['row']}": field
        for row in v2["rows"]
        for field in row["fields"]
        if field["column"] is not None
    }
    for entry in provenance["entries"]:
        cell_ref = entry["cell"].split("!", 1)[1]
        field = fields_by_cell[cell_ref]
        assert field["role"] == entry["agent_role"]
        assert field["sources"] == [
            {
                "file": item["source_file"],
                "location": item["source_location"],
                "text": item["evidence_text"],
            }
            for item in entry["evidence"]
        ]
    revised = {entry["cell"]: entry for entry in provenance["entries"]}[f"{SHEET}!F2"]
    assert revised["agent_role"] == "revision"

    for name in V2_FILES:
        assert_selfcontained((artifacts / name).read_text())


def test_language_variants_embed_identical_data(inputs):
    state = start_run(
        inputs,
        filler=FILLER_OUTPUT,
        review=REVIEW_OUTPUT,
        revision=REVISION_OUTPUT,
    )
    artifacts = artifacts_dir(inputs, state)

    en_v1, zh_v1 = (embedded_data((artifacts / n).read_text()) for n in V1_FILES)
    en_v2, zh_v2 = (embedded_data((artifacts / n).read_text()) for n in V2_FILES)
    assert en_v1 == zh_v1
    assert en_v2 == zh_v2
