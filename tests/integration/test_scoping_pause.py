"""Scoping pause/resume integration tests (ticket #7, plan sections 20, 30).

Seam: the engine entries (run_workflow / resume_workflow) with a
FakeAgentRuntime injected. Assertions inspect artifacts, workbook state,
and the audit store only.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from workflow_app.models import ScopingQuestions
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import resume_workflow, run_workflow
from workflow_app.workspace import RunInputs

CONTRACT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"

SCOPING_OUTPUT = {
    "questions": [
        {"id": "Q1", "question": "Is each source folder one project row?"},
        {"id": "Q2", "question": "Are these folders the full authoritative set?"},
    ]
}

ANSWERS_TEXT = "Q1: One row per source folder.\nQ2: Yes, the set is complete.\n"


def filler_fixture():
    proposal = json.loads((CONTRACT_FIXTURES / "cell_proposal.json").read_text())
    return {"proposals": [proposal]}


PASS_REVIEW = {
    "findings": [
        {
            "cell": "G12",
            "verdict": "PASS",
            "evidence": [],
            "reviewer_comment": "Covered by the deterministic review plan.",
        }
    ]
}


def make_runtimes(*, with_scoping=True):
    outputs = {"filler": filler_fixture(), "reviewer": PASS_REVIEW}
    if with_scoping:
        outputs["scoping"] = SCOPING_OUTPUT
    fake = FakeAgentRuntime(outputs)
    return {role: fake for role in outputs}


def run_inputs(inputs, **overrides):
    values = {
        "source": inputs["source"],
        "workbook": inputs["workbook"],
        "rules": inputs["rules"],
        "workbook_schema": inputs["workbook_schema"],
        **overrides,
    }
    return RunInputs(**values)


def start_paused_run(inputs):
    return run_workflow(
        inputs=run_inputs(inputs),
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
    )


def workspace_of(inputs, state):
    return inputs["runs_root"] / state["run_id"]


def audit_rows(workspace, query, params=()):
    with sqlite3.connect(workspace / "state/audit.sqlite") as conn:
        return conn.execute(query, params).fetchall()


def stage_history(workspace, run_id):
    return audit_rows(
        workspace,
        "SELECT stage, status FROM stages WHERE run_id = ? ORDER BY id",
        (run_id,),
    )


def run_status(workspace, run_id):
    rows = audit_rows(workspace, "SELECT status FROM runs WHERE run_id = ?", (run_id,))
    assert len(rows) == 1
    return rows[0][0]


def test_run_pauses_after_scoping_with_question_artifacts(inputs):
    state = start_paused_run(inputs)
    workspace = workspace_of(inputs, state)

    assert "__interrupt__" in state

    stored = json.loads((workspace / "artifacts/scoping_questions.json").read_text())
    assert stored == ScopingQuestions.model_validate(SCOPING_OUTPUT).model_dump()
    assert Path(state["scoping_questions_path"]) == (
        workspace / "artifacts/scoping_questions.json"
    )

    questions_md = (workspace / "artifacts/scoping_questions.md").read_text()
    for question in SCOPING_OUTPUT["questions"]:
        assert question["id"] in questions_md
        assert question["question"] in questions_md
    assert "scoping_answers.md" in questions_md

    # The answers file is pre-created as a template the user edits.
    answers_template = (workspace / "artifacts/scoping_answers.md").read_text()
    for question in SCOPING_OUTPUT["questions"]:
        assert question["id"] in answers_template

    # Extraction has not started and no output was produced.
    assert not (workspace / "agent_outputs/filler/extraction.json").exists()
    assert not (workspace / "output/final.xlsx").exists()

    # The checkpoint database backs the later resume.
    assert (workspace / "state/checkpoints.sqlite").is_file()


def test_pause_records_paused_status_and_interrupted_stage(inputs):
    state = start_paused_run(inputs)
    workspace = workspace_of(inputs, state)

    assert run_status(workspace, state["run_id"]) == "paused"
    stages = stage_history(workspace, state["run_id"])
    assert ("CLAUDE_SCOPE", "completed") in stages
    # The await stage was entered and then interrupted, never finished.
    assert stages[-1] == ("AWAIT_SCOPING_ANSWERS", "started")


def test_pause_prints_answers_file_and_resume_command(inputs, capsys):
    state = start_paused_run(inputs)
    workspace = workspace_of(inputs, state)

    err = capsys.readouterr().err
    assert str(workspace / "artifacts/scoping_answers.md") in err
    expected_command = (
        f"workflow resume --run-id {state['run_id']} --runs-root {inputs['runs_root']}"
    )
    assert expected_command in err


def test_resume_continues_into_extraction_and_completes(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "artifacts/scoping_answers.md").write_text(ANSWERS_TEXT)

    state = resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
    )

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()
    assert (workspace / "artifacts/run_summary.md").is_file()
    assert Path(state["scoping_answers_path"]) == (
        workspace / "artifacts/scoping_answers.md"
    )
    assert run_status(workspace, state["run_id"]) == "completed"

    stages = stage_history(workspace, state["run_id"])
    await_statuses = [
        status for stage, status in stages if stage == "AWAIT_SCOPING_ANSWERS"
    ]
    # First entry was interrupted; the resumed entry completed.
    assert await_statuses == ["started", "completed"]
    assert ("CLAUDE_FILL", "completed") in stages
    assert stages[-1] == ("FINALIZE", "completed")


def test_resume_passes_answers_to_filler_and_audits_them(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "artifacts/scoping_answers.md").write_text(ANSWERS_TEXT)

    resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
    )

    filler_inputs = json.loads(
        (workspace / "agent_outputs/filler/inputs.json").read_text()
    )
    assert filler_inputs["scoping_answers_path"] == "artifacts/scoping_answers.md"

    events = audit_rows(
        workspace,
        "SELECT kind, payload FROM events WHERE run_id = ?",
        (paused["run_id"],),
    )
    payloads = {kind: json.loads(payload) for kind, payload in events}
    received = payloads["scoping_answers_received"]
    assert received["path"] == "artifacts/scoping_answers.md"
    assert received["sha256"] == hashlib.sha256(ANSWERS_TEXT.encode()).hexdigest()


def test_preprovided_answers_skip_the_scoping_pass(inputs):
    state = run_workflow(
        inputs=run_inputs(inputs, scoping_answers=inputs["scoping_answers"]),
        runs_root=inputs["runs_root"],
        # No scoping fixture: an unexpected scoping invocation would raise.
        runtimes=make_runtimes(with_scoping=False),
    )
    workspace = workspace_of(inputs, state)

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()
    assert (workspace / "artifacts/scoping_answers.md").read_text() == (
        inputs["scoping_answers"].read_text()
    )
    assert Path(state["scoping_answers_path"]) == (
        workspace / "artifacts/scoping_answers.md"
    )

    stage_names = {stage for stage, _ in stage_history(workspace, state["run_id"])}
    assert "CLAUDE_SCOPE" not in stage_names
    assert "AWAIT_SCOPING_ANSWERS" not in stage_names

    filler_inputs = json.loads(
        (workspace / "agent_outputs/filler/inputs.json").read_text()
    )
    assert filler_inputs["scoping_answers_path"] == "artifacts/scoping_answers.md"


def test_missing_preprovided_answers_file_fails_before_run(inputs):
    with pytest.raises(FileNotFoundError, match="scoping answers"):
        run_workflow(
            inputs=run_inputs(
                inputs, scoping_answers=inputs["source"] / "does-not-exist.md"
            ),
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(),
        )
    assert not inputs["runs_root"].exists()


def test_resume_with_deleted_answers_file_reports_a_clear_error(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "artifacts/scoping_answers.md").unlink()

    with pytest.raises(FileNotFoundError, match="scoping answers"):
        resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(),
        )


def test_resume_unknown_run_id_reports_a_clear_error(inputs):
    inputs["runs_root"].mkdir()
    with pytest.raises(FileNotFoundError, match="run workspace"):
        resume_workflow(
            run_id="20990101-000000-aaaaaa",
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(),
        )


def test_resume_of_an_empty_workspace_directory_reports_a_clear_error(inputs):
    (inputs["runs_root"] / "20990101-000000-bbbbbb").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="cannot be resumed"):
        resume_workflow(
            run_id="20990101-000000-bbbbbb",
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(),
        )


def test_resume_without_a_checkpoint_reports_a_clear_error(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "state/checkpoints.sqlite").unlink()

    with pytest.raises(FileNotFoundError, match="resumable checkpoint"):
        resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(),
        )


def test_resume_works_from_a_different_working_directory(inputs, monkeypatch):
    # Start the run with a *relative* runs root, as the CLI default does.
    monkeypatch.chdir(inputs["runs_root"].parent)
    paused = run_workflow(
        inputs=run_inputs(inputs),
        runs_root="runs",
        runtimes=make_runtimes(),
    )
    workspace = inputs["runs_root"] / paused["run_id"]
    (workspace / "artifacts/scoping_answers.md").write_text(ANSWERS_TEXT)

    monkeypatch.chdir(inputs["source"])
    state = resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
    )

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()


def test_failed_resume_no_longer_reports_the_run_as_paused(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "artifacts/scoping_answers.md").write_text(ANSWERS_TEXT)

    # A filler payload violating the extraction contract fails the
    # resumed leg after the pause has been consumed.
    runtimes = make_runtimes()
    runtimes["filler"] = FakeAgentRuntime({"filler": {"proposals": [{"bad": 1}]}})
    with pytest.raises(Exception, match="filler failed"):
        resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=runtimes,
        )

    # The answers were ingested, so 'paused' would be a false fact.
    assert run_status(workspace, paused["run_id"]) == "failed"
