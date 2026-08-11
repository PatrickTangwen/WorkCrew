from fastapi.testclient import TestClient

from tests.integration.conftest import WORKBOOK_SCHEMA_CONFIG
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app

SCOPING_OUTPUT = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
    "questions": [{"id": "Q1", "question": "Is each folder one project?"}],
}


def run_payload(inputs, scoping_answers):
    return {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "rules_file": str(inputs["rules_file"]),
        "scoping_answers": scoping_answers,
        "review_policy": None,
    }


def stream_run(inputs, case, outputs, roles, scoping_answers):
    runtime = FakeAgentRuntime(outputs)
    app = create_app(
        inputs["runs_root"] / case / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"] / case,
            runtimes={role: runtime for role in roles},
        ),
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/runs",
            json=run_payload(inputs, scoping_answers),
        ).json()
        with client.websocket_connect(f"/ws/runs/{created['run_id']}") as websocket:
            events = []
            while not events or events[-1]["type"] not in {
                "paused",
                "completed",
                "failed",
            }:
                events.append(websocket.receive_json())
        record = client.get(f"/api/runs/{created['run_id']}").json()
    return events, record


def phase_changes(events):
    return [
        (event["phase"], event["status"])
        for event in events
        if event["type"] == "phase_change"
    ]


def completed_phases(phases):
    return [
        change
        for phase in phases
        for change in ((phase, "active"), (phase, "completed"))
    ]


def assert_progress_follows_phase_start(events):
    for phase, status in phase_changes(events):
        if status != "active":
            continue
        start = next(
            index
            for index, event in enumerate(events)
            if event.get("phase") == phase
            and event["type"] == "phase_change"
            and event["status"] == "active"
        )
        first_progress = next(
            index
            for index, event in enumerate(events)
            if event.get("phase") == phase and event["type"] == "progress"
        )
        assert start < first_progress


def test_websocket_streams_all_five_engine_event_types_in_lifecycle_order(inputs):
    completed, completed_record = stream_run(
        inputs,
        "completed",
        {
            "scoping": SCOPING_OUTPUT,
            "filler": {"proposals": []},
            "reviewer": {"findings": []},
        },
        {"scoping", "filler", "reviewer"},
        str(inputs["scoping_answers"]),
    )
    paused, paused_record = stream_run(
        inputs,
        "paused",
        {"scoping": SCOPING_OUTPUT},
        {"scoping"},
        None,
    )
    failed, failed_record = stream_run(
        inputs,
        "failed",
        {},
        {"scoping"},
        str(inputs["scoping_answers"]),
    )

    assert completed[-1]["type"] == "completed"
    assert completed_record["status"] == "completed"
    assert paused[-1]["type"] == "paused"
    assert paused_record["status"] == "paused"
    assert failed[-1]["type"] == "failed"
    assert failed_record["status"] == "failed"
    # With no scoping fixture the run now dies at the first agent stage,
    # which is CLAUDE_SCOPE since it precedes the fill (ADR 0032).
    assert failed_record["phase"] == "CLAUDE_SCOPE"
    assert phase_changes(completed) == completed_phases(
        [
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
    )
    assert phase_changes(paused) == [
        *completed_phases(
            [
                "INIT",
                "PREPARE_WORKSPACE",
                "BUILD_MANIFEST",
                "OUTLINE_WORKBOOK",
                "CLAUDE_SCOPE",
                "LOAD_SCHEMA",
            ]
        ),
        ("AWAIT_SCOPING_ANSWERS", "active"),
    ]
    assert phase_changes(failed) == [
        *completed_phases(
            ["INIT", "PREPARE_WORKSPACE", "BUILD_MANIFEST", "OUTLINE_WORKBOOK"]
        ),
        ("CLAUDE_SCOPE", "active"),
        ("CLAUDE_SCOPE", "failed"),
    ]
    assert_progress_follows_phase_start(completed)
    assert_progress_follows_phase_start(paused)
    assert_progress_follows_phase_start(failed)
    assert failed[-2] == {
        "type": "phase_change",
        "timestamp": failed[-2]["timestamp"],
        "phase": "CLAUDE_SCOPE",
        "status": "failed",
    }

    all_events = completed + paused + failed
    assert {event["type"] for event in all_events} == {
        "progress",
        "phase_change",
        "paused",
        "completed",
        "failed",
    }
    assert all(
        event.get("phase") for event in all_events if event["type"] == "progress"
    )
    assert all(
        set(event) == {"type", "timestamp", "phase", "status"}
        for event in all_events
        if event["type"] == "phase_change"
    )


def test_a_reopened_run_replays_its_recorded_events_and_finish_time(inputs):
    """A refresh — or a restart — must not lose a finished run's log."""
    runs_root = inputs["runs_root"] / "replay"
    outputs = {
        "scoping": SCOPING_OUTPUT,
        "filler": {"proposals": []},
        "reviewer": {"findings": []},
    }

    def build_app():
        runtime = FakeAgentRuntime(outputs)
        return create_app(
            runs_root / "missing-static",
            options=ServerOptions(
                home_dir=inputs["source"].parent,
                runs_root=runs_root,
                runtimes={
                    role: runtime for role in ("scoping", "filler", "reviewer")
                },
            ),
        )

    with TestClient(build_app()) as client:
        run_id = client.post(
            "/api/runs",
            json=run_payload(inputs, str(inputs["scoping_answers"])),
        ).json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            streamed = []
            while not streamed or streamed[-1]["type"] != "completed":
                streamed.append(websocket.receive_json())
        live_record = client.get(f"/api/runs/{run_id}").json()

    assert client.get(f"/api/runs/{run_id}/events").json() == streamed
    assert live_record["finished_at"] >= live_record["start_time"]

    # A second server has never seen this run in memory, so everything it
    # reports comes off the workspace on disk.
    with TestClient(build_app()) as restarted:
        assert restarted.get(f"/api/runs/{run_id}/events").json() == streamed
        reopened = restarted.get(f"/api/runs/{run_id}").json()

    assert reopened["finished_at"] >= reopened["start_time"]
    assert reopened["status"] == "completed"


def test_an_unfinished_run_reports_no_finish_time(inputs):
    _, paused_record = stream_run(
        inputs,
        "unfinished",
        {"scoping": SCOPING_OUTPUT},
        {"scoping"},
        None,
    )

    assert paused_record["finished_at"] is None
