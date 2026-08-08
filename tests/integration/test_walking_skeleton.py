"""Walking-skeleton integration tests (ticket #2).

Primary test seam: the workflow engine entry with a FakeAgentRuntime
injected. Assertions inspect only artifacts and workspace state.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow

CONTRACT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"

EXPECTED_SUBDIRS = [
    "input/sources",
    "input/rules",
    "input/workbook",
    "working",
    "agent_outputs/filler",
    "agent_outputs/reviewer",
    "agent_outputs/revision",
    "artifacts",
    "output",
    "state",
    "logs",
]

EXPECTED_STAGES = ["INIT", "PREPARE_WORKSPACE", "CLAUDE_FILL", "FINALIZE"]


def filler_fixture():
    proposal = json.loads((CONTRACT_FIXTURES / "cell_proposal.json").read_text())
    return {"proposals": [proposal]}


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source_documents"
    (source / "India 2008").mkdir(parents=True)
    (source / "India 2008" / "Project_Brief.txt").write_text(
        "Community healthcare delivery project."
    )
    (source / "archive_notes.md").write_text("Top-level archive notes.")

    workbook = tmp_path / "template.xlsx"
    workbook.write_bytes(b"placeholder workbook bytes")

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "naming.md").write_text("Naming conventions.")

    return {
        "source": source,
        "workbook": workbook,
        "rules": rules,
        "runs_root": tmp_path / "runs",
    }


def start_run(inputs, fixture=None):
    runtime = FakeAgentRuntime({"filler": fixture or filler_fixture()})
    return run_workflow(
        source=inputs["source"],
        workbook=inputs["workbook"],
        rules=inputs["rules"],
        runs_root=inputs["runs_root"],
        runtimes={"filler": runtime},
    )


def workspace_of(inputs, state):
    workspace = Path(state["workspace_path"])
    assert workspace == inputs["runs_root"] / state["run_id"]
    return workspace


def snapshot_tree(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_creates_full_workspace_layout(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)
    for subdir in EXPECTED_SUBDIRS:
        assert (workspace / subdir).is_dir(), f"missing {subdir}"


def test_copies_inputs_into_workspace(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    copied_brief = workspace / "input/sources/India 2008/Project_Brief.txt"
    assert copied_brief.read_text() == "Community healthcare delivery project."
    assert (workspace / "input/sources/archive_notes.md").is_file()
    assert (workspace / "input/workbook/template.xlsx").read_bytes() == (
        b"placeholder workbook bytes"
    )
    assert (workspace / "input/rules/naming.md").read_text() == "Naming conventions."


def test_never_modifies_original_inputs(inputs):
    before_sources = snapshot_tree(inputs["source"])
    before_rules = snapshot_tree(inputs["rules"])
    before_workbook = inputs["workbook"].read_bytes()

    start_run(inputs)

    assert snapshot_tree(inputs["source"]) == before_sources
    assert snapshot_tree(inputs["rules"]) == before_rules
    assert inputs["workbook"].read_bytes() == before_workbook


def test_fake_runtime_output_is_replayed_through_the_graph(inputs):
    fixture = filler_fixture()
    state = start_run(inputs, fixture=fixture)
    workspace = workspace_of(inputs, state)

    extraction_path = workspace / "agent_outputs/filler/extraction.json"
    assert Path(state["extraction_path"]) == extraction_path
    assert json.loads(extraction_path.read_text()) == fixture


def test_audit_store_records_run_and_stages(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    db = workspace / "state/audit.sqlite"
    assert db.is_file()
    with sqlite3.connect(db) as conn:
        runs = conn.execute(
            "SELECT run_id, status, started_at, finished_at FROM runs"
        ).fetchall()
        stages = conn.execute(
            "SELECT stage, status FROM stages WHERE run_id = ? ORDER BY id",
            (state["run_id"],),
        ).fetchall()

    assert len(runs) == 1
    run_id, status, started_at, finished_at = runs[0]
    assert run_id == state["run_id"]
    assert status == "completed"
    assert started_at and finished_at

    assert [stage for stage, _ in stages] == EXPECTED_STAGES
    assert all(stage_status == "completed" for _, stage_status in stages)


def test_run_summary_is_produced(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    summary = (workspace / "artifacts/run_summary.md").read_text()
    assert state["run_id"] in summary
    for stage in EXPECTED_STAGES:
        assert stage in summary


def test_stage_progress_lines_go_to_stderr(inputs, capsys):
    state = start_run(inputs)

    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.startswith("[workflow] ")]
    assert any(state["run_id"] in line for line in lines)
    # At least one progress line per graph stage plus start/completion.
    assert len(lines) >= len(EXPECTED_STAGES)


def test_final_state_reports_finalized_phase(inputs):
    state = start_run(inputs)
    assert state["phase"] == "FINALIZE"


def test_missing_source_folder_fails_before_creating_a_run(inputs):
    with pytest.raises(FileNotFoundError):
        run_workflow(
            source=inputs["source"] / "does-not-exist",
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            runs_root=inputs["runs_root"],
            runtimes={"filler": FakeAgentRuntime({"filler": filler_fixture()})},
        )
    assert not inputs["runs_root"].exists()
