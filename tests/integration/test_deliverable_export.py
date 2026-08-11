"""Deliverable export into the source folder (ADR 0035).

Seam: the engine entry with fakes injected. Assertions inspect the
exported directory in the operator's source folder and what a later run
on the same folder ingests.
"""

import json
from pathlib import Path

from tests.integration.conftest import scoping_fixture
from workflow_app.artifacts import deliverable_entries
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import OUTPUT_DIR_NAME, RunInputs

CONTRACT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"


def start_run(inputs):
    proposal = json.loads((CONTRACT_FIXTURES / "cell_proposal.json").read_text())
    outputs = {
        "scoping": scoping_fixture(),
        "filler": {"proposals": [proposal]},
        "reviewer": {
            "findings": [
                {
                    "cell": "G12",
                    "verdict": "PASS",
                    "evidence": [],
                    "reviewer_comment": "Verified against the source.",
                }
            ]
        },
    }
    fake = FakeAgentRuntime(outputs)
    return run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            task=inputs["task"],
            rules_file=inputs["rules_file"],
            scoping_answers=inputs["scoping_answers"],
        ),
        runs_root=inputs["runs_root"],
        runtimes={role: fake for role in outputs},
    )


def export_dir(inputs, state):
    return inputs["source"] / OUTPUT_DIR_NAME / state["run_id"]


def test_export_matches_the_run_artifact_catalog_exactly(inputs):
    state = start_run(inputs)
    workspace = Path(inputs["runs_root"]) / state["run_id"]

    published = deliverable_entries(workspace)
    exported = export_dir(inputs, state)

    assert {path.name for path in exported.iterdir()} == set(published)
    # Same bytes, not just the same names.
    for name, entry in published.items():
        assert (exported / name).read_bytes() == entry.path.read_bytes()
    assert "final.xlsx" in published
    assert "review_explorer_v2.html" in published
    # The summary reports the closed run, so it must be exported too.
    assert "Status: completed" in (exported / "run_summary.md").read_text()


def test_each_run_exports_into_its_own_directory(inputs):
    first = start_run(inputs)
    second = start_run(inputs)

    assert first["run_id"] != second["run_id"]
    for state in (first, second):
        assert (export_dir(inputs, state) / "final.xlsx").is_file()


def test_a_later_run_does_not_ingest_the_previous_run_deliverables(inputs):
    first = start_run(inputs)
    assert export_dir(inputs, first).is_dir()

    second = start_run(inputs)
    copied_sources = Path(inputs["runs_root"]) / second["run_id"] / "input" / "sources"

    assert not (copied_sources / OUTPUT_DIR_NAME).exists()
    # The operator's own documents still come through untouched.
    assert (copied_sources / "India 2008" / "Project_Brief.txt").is_file()
    manifest = json.loads(
        (
            Path(inputs["runs_root"]) / second["run_id"] / "artifacts" / "manifest.json"
        ).read_text()
    )
    assert not any(
        OUTPUT_DIR_NAME in entry["path"] for entry in manifest["files"]
    ), "a previous run's deliverables must not appear as source documents"


def test_a_source_directory_named_like_the_export_is_still_ingested(inputs):
    # Only the export directory at the source root is skipped; one with
    # the same name deeper in the tree is the operator's own document.
    nested = inputs["source"] / "India 2008" / OUTPUT_DIR_NAME
    nested.mkdir()
    (nested / "operator_notes.md").write_text("Not ours.")

    state = start_run(inputs)
    copied_sources = Path(inputs["runs_root"]) / state["run_id"] / "input" / "sources"

    assert (
        copied_sources / "India 2008" / OUTPUT_DIR_NAME / "operator_notes.md"
    ).is_file()
