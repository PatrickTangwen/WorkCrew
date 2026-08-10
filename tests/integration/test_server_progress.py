from fastapi.testclient import TestClient

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app


def run_payload(inputs, scoping_answers):
    return {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "rules": str(inputs["rules"]),
        "workbook_schema": str(inputs["workbook_schema"]),
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
        {"filler": {"proposals": []}, "reviewer": {"findings": []}},
        {"filler", "reviewer"},
        str(inputs["scoping_answers"]),
    )
    paused, paused_record = stream_run(
        inputs,
        "paused",
        {
            "scoping": {
                "questions": [{"id": "Q1", "question": "Is each folder one project?"}]
            }
        },
        {"scoping"},
        None,
    )
    failed, failed_record = stream_run(
        inputs,
        "failed",
        {},
        {"filler"},
        str(inputs["scoping_answers"]),
    )

    assert completed[-1]["type"] == "completed"
    assert completed_record["status"] == "completed"
    assert paused[-1]["type"] == "paused"
    assert paused_record["status"] == "paused"
    assert failed[-1]["type"] == "failed"
    assert failed_record["status"] == "failed"
    assert failed_record["phase"] == "CLAUDE_FILL"
    assert phase_changes(completed) == completed_phases(
        [
            "INIT",
            "PREPARE_WORKSPACE",
            "BUILD_MANIFEST",
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
                "LOAD_SCHEMA",
                "CLAUDE_SCOPE",
            ]
        ),
        ("AWAIT_SCOPING_ANSWERS", "active"),
    ]
    assert phase_changes(failed) == [
        *completed_phases(
            ["INIT", "PREPARE_WORKSPACE", "BUILD_MANIFEST", "LOAD_SCHEMA"]
        ),
        ("CLAUDE_FILL", "active"),
        ("CLAUDE_FILL", "failed"),
    ]
    assert_progress_follows_phase_start(completed)
    assert_progress_follows_phase_start(paused)
    assert_progress_follows_phase_start(failed)
    assert failed[-2] == {
        "type": "phase_change",
        "timestamp": failed[-2]["timestamp"],
        "phase": "CLAUDE_FILL",
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
