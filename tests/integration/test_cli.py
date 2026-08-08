"""CLI tests: `workflow run` is a thin shell over the engine entry.

Tests call main() directly with no mocking of internals; during
fake-first development the CLI wires in the FakeAgentRuntime itself.
"""

import pytest

from workflow_app.cli import main


def run_args(inputs):
    return [
        "run",
        "--source",
        str(inputs["source"]),
        "--workbook",
        str(inputs["workbook"]),
        "--rules",
        str(inputs["rules"]),
        "--workbook-schema",
        str(inputs["workbook_schema"]),
        "--runs-root",
        str(inputs["runs_root"]),
    ]


def test_run_completes_and_produces_a_workspace(inputs):
    assert main(run_args(inputs)) == 0

    run_dirs = list(inputs["runs_root"].iterdir())
    assert len(run_dirs) == 1
    workspace = run_dirs[0]
    assert (workspace / "artifacts/run_summary.md").is_file()
    assert (workspace / "state/audit.sqlite").is_file()
    assert (workspace / "agent_outputs/filler/extraction.json").is_file()


def test_run_emits_progress_on_stderr(inputs, capsys):
    main(run_args(inputs))
    err = capsys.readouterr().err
    assert "[workflow] Starting run " in err
    assert "[workflow] Run complete." in err


def test_missing_source_reports_error_and_nonzero_exit(inputs, capsys):
    inputs["source"] = inputs["source"] / "does-not-exist"
    exit_code = main(run_args(inputs))
    assert exit_code == 2
    assert "not found" in capsys.readouterr().err


def test_malformed_schema_config_reports_error_and_nonzero_exit(inputs, capsys):
    inputs["workbook_schema"].write_text("{not json")
    exit_code = main(run_args(inputs))
    assert exit_code == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_missing_required_arguments_exit_nonzero(inputs, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--source", str(inputs["source"])])
    assert excinfo.value.code != 0
