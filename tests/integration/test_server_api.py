from fastapi.testclient import TestClient

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app

SCOPING_OUTPUT = {
    "questions": [
        {"id": "Q1", "question": "What is one row?", "type": "text"},
        {
            "id": "Q2",
            "question": "Which period applies?",
            "type": "single_select",
            "options": [
                {"value": "spring", "label": "Spring"},
                {"value": "fall", "label": "Fall"},
            ],
        },
        {
            "id": "Q3",
            "question": "Which folders are authoritative?",
            "type": "multi_select",
            "options": [
                {"value": "alpha", "label": "Alpha"},
                {"value": "beta", "label": "Beta"},
            ],
        },
        {"id": "Q4", "question": "Is this set complete?", "type": "confirm"},
    ]
}


def test_run_api_executes_the_real_engine_with_fake_runtimes(inputs):
    runtime = FakeAgentRuntime(
        {"filler": {"proposals": []}, "reviewer": {"findings": []}}
    )
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={"filler": runtime, "reviewer": runtime},
        ),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "rules": str(inputs["rules"]),
        "workbook_schema": str(inputs["workbook_schema"]),
        "scoping_answers": str(inputs["scoping_answers"]),
        "review_policy": None,
    }

    with TestClient(app) as client:
        created = client.post("/api/runs", json=payload)
        run_id = created.json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            events = []
            while not events or events[-1]["type"] != "completed":
                events.append(websocket.receive_json())
        run = client.get(f"/api/runs/{run_id}").json()

    assert created.status_code == 201
    assert run["status"] == "completed"
    assert run["phase"] == "FINALIZE"
    assert (inputs["runs_root"] / run_id / "output" / "final.xlsx").is_file()
    assert events[-1]["type"] == "completed"
    assert any(event["type"] == "progress" for event in events)
    phase_changes = [
        (event["phase"], event["status"])
        for event in events
        if event["type"] == "phase_change"
    ]
    phases = [
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
    assert phase_changes == [
        change
        for phase in phases
        for change in ((phase, "active"), (phase, "completed"))
    ]


def test_resume_api_writes_answers_and_restarts_the_real_engine(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": SCOPING_OUTPUT,
            "filler": {"proposals": []},
            "reviewer": {"findings": []},
        }
    )
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={role: runtime for role in ("scoping", "filler", "reviewer")},
        ),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "rules": str(inputs["rules"]),
        "workbook_schema": str(inputs["workbook_schema"]),
        "scoping_answers": None,
        "review_policy": None,
    }

    with TestClient(app) as client:
        created = client.post("/api/runs", json=payload)
        run_id = created.json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            events = []
            while not events or events[-1]["type"] != "paused":
                events.append(websocket.receive_json())

            resumed = client.post(
                f"/api/runs/{run_id}/resume",
                json={
                    "answers": {
                        "Q1": "One source folder.",
                        "Q2": "fall",
                        "Q3": ["alpha", "beta"],
                        "Q4": True,
                    }
                },
            )
            assert resumed.status_code == 202
            assert resumed.json()["status"] == "running"
            while events[-1]["type"] != "completed":
                events.append(websocket.receive_json())

        run = client.get(f"/api/runs/{run_id}").json()

    assert run["status"] == "completed"
    assert events[-1]["type"] == "completed"
    answers = (
        inputs["runs_root"] / run_id / "artifacts/scoping_answers.md"
    ).read_text()
    assert (
        answers
        == """# Scoping answers

## Q1

> What is one row?

One source folder.

## Q2

> Which period applies?

Fall

## Q3

> Which folders are authoritative?

- Alpha
- Beta

## Q4

> Is this set complete?

Yes
"""
    )
