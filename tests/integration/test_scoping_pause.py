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

from tests.integration.conftest import WORKBOOK_SCHEMA_CONFIG
from workflow_app.models import ScopingQuestionRound
from workflow_app.reports import replace_scoping_round
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import resume_workflow, run_workflow
from workflow_app.workflow.graph import MAX_SCOPING_ROUNDS
from workflow_app.workspace import RunInputs

CONTRACT_FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"

SCOPING_OUTPUT = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
    "questions": [
        {"id": "Q1", "question": "Is each source folder one project row?"},
        {"id": "Q2", "question": "Are these folders the full authoritative set?"},
    ],
}

SCOPING_DONE = {"workbook_schema": WORKBOOK_SCHEMA_CONFIG, "questions": []}

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


def make_runtimes(scoping=None):
    # A resume is a fresh process in production, so its runtimes start
    # over: resuming tests pass SCOPING_DONE, which is what a real pass
    # returns once it has read the answers and has nothing left to ask.
    outputs = {
        "scoping": scoping if scoping is not None else [SCOPING_OUTPUT, SCOPING_DONE],
        "filler": filler_fixture(),
        "reviewer": PASS_REVIEW,
    }
    fake = FakeAgentRuntime(outputs)
    return {role: fake for role in outputs}


def run_inputs(inputs, **overrides):
    values = {
        "source": inputs["source"],
        "workbook": inputs["workbook"],
        "task": inputs["task"],
        "rules_file": inputs["rules_file"],
        **overrides,
    }
    return RunInputs(**values)


def start_paused_run(inputs):
    return run_workflow(
        inputs=run_inputs(inputs),
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
    )


def start_run_without_questions(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": {"workbook_schema": WORKBOOK_SCHEMA_CONFIG, "questions": []},
            "filler": filler_fixture(),
            "reviewer": PASS_REVIEW,
        }
    )
    return run_workflow(
        inputs=run_inputs(inputs),
        runs_root=inputs["runs_root"],
        runtimes={role: runtime for role in ("scoping", "filler", "reviewer")},
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
    assert (
        stored
        == ScopingQuestionRound(
            round=1,
            questions=SCOPING_OUTPUT["questions"],
        ).model_dump()
    )
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
        runtimes=make_runtimes(scoping=SCOPING_DONE),
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
        runtimes=make_runtimes(scoping=SCOPING_DONE),
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


def test_preprovided_answers_skip_the_pause_but_not_the_scoping_pass(inputs):
    # The scoping pass produces the schema (ADR 0032), so it always runs;
    # pre-provided answers only spare the operator the interrupt.
    state = run_workflow(
        inputs=run_inputs(inputs, scoping_answers=inputs["scoping_answers"]),
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(),
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
    assert "CLAUDE_SCOPE" in stage_names
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
            runtimes=make_runtimes(scoping=SCOPING_DONE),
        )


def test_resume_unknown_run_id_reports_a_clear_error(inputs):
    inputs["runs_root"].mkdir()
    with pytest.raises(FileNotFoundError, match="run workspace"):
        resume_workflow(
            run_id="20990101-000000-aaaaaa",
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(scoping=SCOPING_DONE),
        )


def test_resume_of_an_empty_workspace_directory_reports_a_clear_error(inputs):
    (inputs["runs_root"] / "20990101-000000-bbbbbb").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="cannot be resumed"):
        resume_workflow(
            run_id="20990101-000000-bbbbbb",
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(scoping=SCOPING_DONE),
        )


def test_resume_without_a_checkpoint_reports_a_clear_error(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "state/checkpoints.sqlite").unlink()

    with pytest.raises(FileNotFoundError, match="resumable checkpoint"):
        resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(scoping=SCOPING_DONE),
        )


def test_resume_refuses_a_run_from_before_agent_derived_schemas(inputs):
    run_id = "20260809-120000-legacy"
    workspace = inputs["runs_root"] / run_id
    state_dir = workspace / "state"
    state_dir.mkdir(parents=True)
    with sqlite3.connect(state_dir / "audit.sqlite") as conn:
        conn.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                source_path TEXT NOT NULL,
                workbook_path TEXT NOT NULL,
                rules_path TEXT NOT NULL,
                workbook_schema_path TEXT NOT NULL,
                scoping_answers_path TEXT,
                review_policy_path TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO runs VALUES (?, 'paused', ?, NULL, ?, ?, ?, ?, NULL, NULL)",
            (
                run_id,
                "2026-08-09T12:00:00+00:00",
                str(inputs["source"]),
                str(inputs["workbook"]),
                str(inputs["rules_file"].parent),
                str(workspace / "legacy-schema.json"),
            ),
        )
    (state_dir / "checkpoints.sqlite").touch()

    with pytest.raises(ValueError, match="predates agent-derived workbook schemas"):
        resume_workflow(
            run_id=run_id,
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(scoping=SCOPING_DONE),
        )

    assert run_status(workspace, run_id) == "paused"


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
        runtimes=make_runtimes(scoping=SCOPING_DONE),
    )

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()


def test_failed_resume_no_longer_reports_the_run_as_paused(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    (workspace / "artifacts/scoping_answers.md").write_text(ANSWERS_TEXT)

    # A filler payload violating the extraction contract fails the
    # resumed leg after the pause has been consumed.
    runtimes = make_runtimes(scoping=SCOPING_DONE)
    runtimes["filler"] = FakeAgentRuntime({"filler": {"proposals": [{"bad": 1}]}})
    with pytest.raises(Exception, match="filler failed"):
        resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=runtimes,
        )

    # The answers were ingested, so 'paused' would be a false fact.
    assert run_status(workspace, paused["run_id"]) == "failed"


def test_a_scoping_pass_with_no_questions_does_not_pause(inputs):
    # Whether the run stops to ask is the scoping agent's call: nothing
    # to ask means no pause and no empty form for the operator.
    state = start_run_without_questions(inputs)
    workspace = workspace_of(inputs, state)

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()

    stage_names = {stage for stage, _ in stage_history(workspace, state["run_id"])}
    assert "CLAUDE_SCOPE" in stage_names
    assert "AWAIT_SCOPING_ANSWERS" not in stage_names


def test_the_filler_still_gets_an_answers_document_when_nothing_was_asked(inputs):
    # CLAUDE_FILL reads the answers file unconditionally, so skipping the
    # pause must not skip writing one.
    state = start_run_without_questions(inputs)
    workspace = workspace_of(inputs, state)

    assert Path(state["scoping_answers_path"]) == (
        workspace / "artifacts/scoping_answers.md"
    )
    answers = (workspace / "artifacts/scoping_answers.md").read_text()
    assert "had no questions" in answers
    assert "(your answer here)" not in answers

    filler_inputs = json.loads(
        (workspace / "agent_outputs/filler/inputs.json").read_text()
    )
    assert filler_inputs["scoping_answers_path"] == "artifacts/scoping_answers.md"


SECOND_ROUND = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
    "questions": [
        {"id": "Q1", "question": "Which mapping applies to the folders you flagged?"}
    ],
}


def answer_open_round(workspace, text):
    round_number = json.loads(
        (workspace / "artifacts/scoping_questions.json").read_text()
    )["round"]
    replace_scoping_round(
        workspace / "artifacts/scoping_answers.md",
        round_number,
        text,
    )


def test_answers_feed_a_second_round_the_pass_asks_for(inputs):
    # The pass reads what was answered and decides for itself whether
    # anything is still open (ADR 0032).
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    answer_open_round(workspace, "## Round 1\n\nOne row per folder.\n")

    second = resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(scoping=[SECOND_ROUND, SCOPING_DONE]),
    )

    assert "__interrupt__" in second
    questions = json.loads((workspace / "artifacts/scoping_questions.json").read_text())
    assert questions["questions"][0]["question"].startswith("Which mapping")

    answer_open_round(workspace, "## Round 2\n\nUse the broader region.\n")
    final = resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(scoping=SCOPING_DONE),
    )

    assert "__interrupt__" not in final
    assert (workspace / "output/final.xlsx").is_file()


def test_each_round_is_kept_in_the_transcript(inputs):
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)
    answer_open_round(workspace, "## Round 1\n\nOne row per folder.\n")

    resume_workflow(
        run_id=paused["run_id"],
        runs_root=inputs["runs_root"],
        runtimes=make_runtimes(scoping=[SECOND_ROUND, SCOPING_DONE]),
    )

    transcript = (workspace / "artifacts/scoping_answers.md").read_text()
    assert "## Round 1" in transcript
    assert "One row per folder." in transcript
    assert "## Round 2" in transcript


def test_the_run_stops_asking_after_the_round_cap(inputs):
    # An agent that keeps asking must not hold the operator forever.
    paused = start_paused_run(inputs)
    workspace = workspace_of(inputs, paused)

    state = paused
    for round_number in range(2, MAX_SCOPING_ROUNDS + 2):
        answer_open_round(workspace, f"## Round {round_number - 1}\n\nStill fine.\n")
        state = resume_workflow(
            run_id=paused["run_id"],
            runs_root=inputs["runs_root"],
            runtimes=make_runtimes(scoping=SECOND_ROUND),
        )
        if "__interrupt__" not in state:
            break

    assert "__interrupt__" not in state
    assert (workspace / "output/final.xlsx").is_file()

    payloads = {
        kind: json.loads(payload)
        for kind, payload in audit_rows(
            workspace,
            "SELECT kind, payload FROM events WHERE run_id = ?",
            (paused["run_id"],),
        )
    }
    assert payloads["scoping_rounds_exhausted"]["rounds"] == MAX_SCOPING_ROUNDS
