"""Walking-skeleton integration tests (ticket #2).

Primary test seam: the workflow engine entry with a FakeAgentRuntime
injected. Assertions inspect only artifacts and workspace state.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from tests.integration.conftest import scoping_fixture
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import OUTPUT_DIR_NAME, RunInputs

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

EXPECTED_STAGES = [
    "INIT",
    "PREPARE_WORKSPACE",
    "BUILD_MANIFEST",
    "OUTLINE_WORKBOOK",
    "CLAUDE_SCOPE",
    "LOAD_SCHEMA",
    "CLAUDE_FILL",
    "VALIDATE",
    "WRITE_DRAFT",
    "CODEX_REVIEW",
    "FINALIZE",
]


def filler_fixture():
    proposal = json.loads((CONTRACT_FIXTURES / "cell_proposal.json").read_text())
    return {"proposals": [proposal]}


def pass_review(cell="G12"):
    return {
        "findings": [
            {
                "cell": cell,
                "verdict": "PASS",
                "evidence": [],
                "reviewer_comment": "Covered by the deterministic review plan.",
            }
        ]
    }


def run_inputs(inputs, **overrides):
    values = {
        "source": inputs["source"],
        "workbook": inputs["workbook"],
        "task": inputs["task"],
        "rules_file": inputs["rules_file"],
        "scoping_answers": inputs["scoping_answers"],
        **overrides,
    }
    return RunInputs(**values)


def start_run(inputs, fixture=None, scoping=None, run_inputs_kwargs=None):
    runtime = FakeAgentRuntime(
        {
            "scoping": scoping or scoping_fixture(),
            "filler": fixture or filler_fixture(),
            "reviewer": pass_review(),
        }
    )
    return run_workflow(
        inputs=run_inputs(inputs, **(run_inputs_kwargs or {})),
        runs_root=inputs["runs_root"],
        runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
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


def test_the_run_id_names_the_workspace_after_the_source_folder(inputs):
    state = start_run(inputs)

    assert state["run_id"].startswith("source-documents-")
    assert (Path(inputs["runs_root"]) / state["run_id"]).is_dir()


def test_copies_inputs_into_workspace(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    copied_brief = workspace / "input/sources/India 2008/Project_Brief.txt"
    assert copied_brief.read_text() == "Community healthcare delivery project."
    assert (workspace / "input/sources/archive_notes.md").is_file()
    assert (workspace / "input/workbook/template.xlsx").read_bytes() == (
        inputs["workbook"].read_bytes()
    )
    assert (workspace / "input/rules/rules.md").read_text() == "Naming conventions."
    assert (workspace / "input/task.md").read_text() == inputs["task"]


def test_prose_rules_land_where_a_rules_file_would(inputs):
    state = start_run(
        inputs, run_inputs_kwargs={"rules_file": None, "rules_text": "Prose."}
    )
    workspace = workspace_of(inputs, state)

    assert (workspace / "input/rules/rules.md").read_text() == "Prose."


def test_a_run_without_rules_leaves_the_rules_directory_empty(inputs):
    state = start_run(inputs, run_inputs_kwargs={"rules_file": None})
    workspace = workspace_of(inputs, state)

    assert (workspace / "input/rules").is_dir()
    assert list((workspace / "input/rules").iterdir()) == []


def test_never_modifies_original_inputs(inputs):
    before_sources = snapshot_tree(inputs["source"])
    before_rules = inputs["rules_file"].read_text()
    before_workbook = inputs["workbook"].read_bytes()

    state = start_run(inputs)

    # The run adds its deliverables to the source folder (ADR 0035) and
    # changes nothing that was already there.
    after_sources = snapshot_tree(inputs["source"])
    export_root = Path(OUTPUT_DIR_NAME) / state["run_id"]
    kept = {
        path: content
        for path, content in after_sources.items()
        if not path.is_relative_to(export_root)
    }
    assert kept == before_sources
    assert len(after_sources) > len(before_sources)
    assert inputs["rules_file"].read_text() == before_rules
    assert inputs["workbook"].read_bytes() == before_workbook


def test_fake_runtime_output_is_replayed_through_the_graph(inputs):
    fixture = filler_fixture()
    state = start_run(inputs, fixture=fixture)
    workspace = workspace_of(inputs, state)

    raw_path = workspace / "agent_outputs/filler/extraction.json"
    assert json.loads(raw_path.read_text()) == fixture
    # After VALIDATE the state points at the canonical artifact.
    assert Path(state["extraction_path"]) == workspace / "artifacts/extraction.json"


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


def test_manifest_artifact_lists_all_copied_sources(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    manifest = json.loads((workspace / "artifacts/manifest.json").read_text())
    entries = {entry["path"]: entry for entry in manifest["files"]}

    assert set(entries) == {
        "India 2008/Project_Brief.txt",
        "archive_notes.md",
        "legacy_archive.zip",
    }
    brief = entries["India 2008/Project_Brief.txt"]
    assert brief["status"] == "ok"
    assert brief["type"] == "txt"
    assert len(brief["sha256"]) == 64
    assert entries["legacy_archive.zip"]["status"] == "UNSUPPORTED"
    assert Path(state["manifest_path"]) == workspace / "artifacts/manifest.json"


def test_validated_schema_is_stored_as_artifact(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)

    stored = json.loads((workspace / "artifacts/workbook_schema.json").read_text())
    sheet = stored["sheets"][0]
    assert sheet["name"] == "7) Practicum Courses"
    assert sheet["target"] is True
    assert sheet["fields"]["Project ID*"]["required"] is True
    assert Path(state["schema_path"]) == workspace / "artifacts/workbook_schema.json"


def test_a_malformed_agent_schema_is_retried_then_fails_the_run(inputs):
    # The schema arrives through the scoping contract (ADR 0032), so a
    # schema with no target sheet is a retryable agent failure rather
    # than the pre-run gate it used to be.
    with pytest.raises(Exception, match="scoping failed after 3 attempts"):
        start_run(inputs, scoping={"workbook_schema": {"sheets": []}, "questions": []})


def test_missing_source_folder_fails_before_creating_a_run(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": scoping_fixture(),
            "filler": filler_fixture(),
            "reviewer": {"findings": []},
        }
    )
    with pytest.raises(FileNotFoundError):
        run_workflow(
            inputs=run_inputs(inputs, source=inputs["source"] / "does-not-exist"),
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        )
    assert not inputs["runs_root"].exists()


def test_review_policy_reaches_reviewer_inputs(inputs, tmp_path):
    # A provided policy YAML (plan section 25) is copied into the
    # workspace, stored canonically, and passed into the Reviewer inputs.
    policy_yaml = tmp_path / "review_policy.yaml"
    policy_yaml.write_text(
        "review:\n"
        "  coverage: full\n"
        "  strict_fields: ['Project ID*']\n"
        "  high_confidence_sampling_per_record: 3\n"
    )
    runtime = FakeAgentRuntime(
        {
            "scoping": scoping_fixture(),
            "filler": filler_fixture(),
            "reviewer": pass_review(),
        }
    )
    state = run_workflow(
        inputs=run_inputs(inputs, review_policy=policy_yaml),
        runs_root=inputs["runs_root"],
        runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
    )
    workspace = workspace_of(inputs, state)

    canonical = json.loads((workspace / "artifacts" / "review_policy.json").read_text())
    assert canonical == {
        "coverage": "full",
        "strict_fields": ["Project ID*"],
        "high_confidence_sampling_per_record": 3,
    }

    reviewer_inputs = json.loads(
        (workspace / "agent_outputs" / "reviewer" / "inputs.json").read_text()
    )
    assert reviewer_inputs["review_policy"] == canonical
    assert reviewer_inputs["draft_workbook"] == "working/draft.xlsx"
    assert reviewer_inputs["review_targets"] == [
        {"cell": "G12", "reason": "full coverage"}
    ]


def test_missing_planned_review_target_fails_deterministically(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": scoping_fixture(),
            "filler": filler_fixture(),
            "reviewer": {"findings": []},
        }
    )

    with pytest.raises(ValueError, match="planned targets.*G12"):
        run_workflow(
            inputs=run_inputs(inputs),
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        )


def test_default_review_policy_applies_when_none_is_provided(inputs):
    state = start_run(inputs)
    workspace = workspace_of(inputs, state)
    canonical = json.loads((workspace / "artifacts" / "review_policy.json").read_text())
    assert canonical == {
        "coverage": "sampled",
        "strict_fields": [],
        "high_confidence_sampling_per_record": 2,
    }


def test_unknown_strict_field_fails_once_the_schema_exists(inputs, tmp_path):
    # The cross-check moved from the engine's pre-run gate into
    # LOAD_SCHEMA: the schema it checks against only exists after the
    # scoping pass has produced it (ADR 0032).
    policy_yaml = tmp_path / "review_policy.yaml"
    policy_yaml.write_text("review:\n  strict_fields: ['No Such Field']\n")
    with pytest.raises(ValueError, match="No Such Field"):
        start_run(inputs, run_inputs_kwargs={"review_policy": policy_yaml})


def test_a_runs_root_inside_the_source_folder_is_refused(inputs):
    # copy_inputs would otherwise copy the sources into their own
    # subdirectory and recurse until the OS refuses the path length.
    nested_runs_root = inputs["source"] / "runs"

    with pytest.raises(ValueError, match="would sit inside the source folder"):
        run_workflow(
            inputs=run_inputs(inputs),
            runs_root=nested_runs_root,
            runtimes={},
        )

    assert not nested_runs_root.exists()
