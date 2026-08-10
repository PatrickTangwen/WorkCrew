"""CLI tests: `workflow run` is a thin shell over the engine entry.

Tests call main() directly with no mocking of internals, always with
`--runtimes fake` so no test spends agent quota; live is the CLI
default (asserted below) and is exercised by the smoke tests.
"""

import pytest

from workflow_app import cli
from workflow_app.cli import build_parser, main


def run_args(inputs):
    return [
        "run",
        "--source",
        str(inputs["source"]),
        "--workbook",
        str(inputs["workbook"]),
        "--task",
        inputs["task"],
        "--rules-file",
        str(inputs["rules_file"]),
        "--runs-root",
        str(inputs["runs_root"]),
        "--runtimes",
        "fake",
    ]


def test_run_pauses_then_resume_completes(inputs, capsys):
    assert main(run_args(inputs)) == 0

    run_dirs = list(inputs["runs_root"].iterdir())
    assert len(run_dirs) == 1
    workspace = run_dirs[0]
    assert (workspace / "artifacts/scoping_questions.md").is_file()
    assert (workspace / "state/audit.sqlite").is_file()
    assert not (workspace / "output/final.xlsx").exists()

    err = capsys.readouterr().err
    assert "[workflow] Starting run " in err
    assert "Run paused" in err
    resume_command = f"workflow resume --run-id {workspace.name}"
    assert resume_command in err

    (workspace / "artifacts/scoping_answers.md").write_text("Q1: Confirmed.\n")
    resume_args = [
        "resume",
        "--run-id",
        workspace.name,
        "--runs-root",
        str(inputs["runs_root"]),
        "--runtimes",
        "fake",
    ]
    assert main(resume_args) == 0

    assert (workspace / "artifacts/run_summary.md").is_file()
    assert (workspace / "agent_outputs/filler/extraction.json").is_file()
    assert (workspace / "output/final.xlsx").is_file()
    assert "[workflow] Run complete." in capsys.readouterr().err


def test_run_with_preprovided_answers_completes_without_pause(inputs, capsys):
    args = run_args(inputs) + ["--scoping-answers", str(inputs["scoping_answers"])]
    assert main(args) == 0

    workspace = next(inputs["runs_root"].iterdir())
    assert (workspace / "output/final.xlsx").is_file()
    err = capsys.readouterr().err
    assert "Run paused" not in err
    assert "[workflow] Run complete." in err


def test_resume_unknown_run_id_reports_error_and_nonzero_exit(inputs, capsys):
    inputs["runs_root"].mkdir()
    exit_code = main(
        [
            "resume",
            "--run-id",
            "20990101-000000-aaaaaa",
            "--runs-root",
            str(inputs["runs_root"]),
            "--runtimes",
            "fake",
        ]
    )
    assert exit_code == 2
    assert "run workspace" in capsys.readouterr().err


def test_missing_source_reports_error_and_nonzero_exit(inputs, capsys):
    inputs["source"] = inputs["source"] / "does-not-exist"
    exit_code = main(run_args(inputs))
    assert exit_code == 2
    assert "not found" in capsys.readouterr().err


def test_an_empty_task_reports_error_and_nonzero_exit(inputs, capsys):
    # The schema is derived from the task now (ADR 0032), so the task is
    # what the CLI can still reject before the run starts.
    args = [arg if arg != inputs["task"] else "   " for arg in run_args(inputs)]
    exit_code = main(args)
    assert exit_code == 2
    assert "task description must not be empty" in capsys.readouterr().err


def test_rules_text_and_rules_file_are_mutually_exclusive(inputs, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(run_args(inputs) + ["--rules-text", "Prose rules."])
    assert excinfo.value.code != 0


def test_missing_required_arguments_exit_nonzero(inputs, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "--source", str(inputs["source"])])
    assert excinfo.value.code != 0


def test_live_runtimes_are_the_default(inputs):
    # The product default is the live pipeline (plan section 32: fake
    # first, "only then connect real agents"); parsed without invoking.
    args = build_parser().parse_args(run_args(inputs)[:-2])
    assert args.runtimes == "live"


def test_pinned_model_defaults(inputs):
    # Models and review effort are pinned (ADR 0020) so CLI upgrades or
    # account-default changes never silently shift engine behavior.
    args = build_parser().parse_args(run_args(inputs)[:-2])
    assert args.claude_model == "claude-opus-4-6[1m]"
    assert args.codex_model == "gpt-5.6-sol"
    assert args.codex_effort == "high"


def test_ui_command_starts_the_web_server_on_the_default_port(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ui", lambda port: calls.append(port))

    assert main(["ui"]) == 0
    assert calls == [8470]


def test_ui_command_starts_the_web_server_on_an_explicit_port(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_ui", lambda port: calls.append(port))

    assert main(["ui", "--port", "9000"]) == 0
    assert calls == [9000]


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_ui_command_rejects_invalid_ports_before_startup(port, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "run_ui", lambda requested: calls.append(requested))

    with pytest.raises(SystemExit) as excinfo:
        main(["ui", "--port", port])

    assert excinfo.value.code == 2
    assert "--port" in capsys.readouterr().err
    assert calls == []


def test_ui_keyboard_interrupt_stops_without_a_traceback(monkeypatch, capsys):
    def interrupt(port):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_ui", interrupt)

    assert main(["ui"]) == 130
    assert capsys.readouterr().err == "[workflow] WorkCrew UI stopped.\n"
