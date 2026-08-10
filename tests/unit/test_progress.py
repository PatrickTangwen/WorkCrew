from datetime import datetime

from workflow_app.progress import ProgressReporter, emit


def test_emit_preserves_cli_output_and_calls_the_optional_callback(capsys):
    events = []

    emit("Validating proposals...", events.append)

    assert capsys.readouterr().err == "[workflow] Validating proposals...\n"
    assert len(events) == 1
    assert events[0]["type"] == "progress"
    assert events[0]["message"] == "Validating proposals..."
    assert datetime.fromisoformat(events[0]["timestamp"]).tzinfo is not None


def test_emit_without_a_callback_keeps_cli_behavior(capsys):
    emit("Starting run...")

    assert capsys.readouterr().err == "[workflow] Starting run...\n"


def test_reporter_adds_the_current_phase_to_progress_events(capsys):
    events = []
    reporter = ProgressReporter(events.append)
    reporter.phase_change("CLAUDE_FILL", "active")

    reporter.emit("Starting Filler...")

    assert capsys.readouterr().err == "[workflow] Starting Filler...\n"
    assert events[1] == {
        "type": "progress",
        "timestamp": events[1]["timestamp"],
        "phase": "CLAUDE_FILL",
        "message": "Starting Filler...",
    }
