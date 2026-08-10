from fastapi.testclient import TestClient

from tests.integration.conftest import WORKBOOK_SCHEMA_CONFIG, scoping_fixture
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app

SCOPING_DONE = {"workbook_schema": WORKBOOK_SCHEMA_CONFIG, "questions": []}

SCOPING_OUTPUT = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
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
    ],
}


def test_run_api_executes_the_real_engine_with_fake_runtimes(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": scoping_fixture(),
            "filler": {"proposals": []},
            "reviewer": {"findings": []},
        }
    )
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        ),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "rules_file": str(inputs["rules_file"]),
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
        "OUTLINE_WORKBOOK",
        "CLAUDE_SCOPE",
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
            "scoping": [SCOPING_OUTPUT, SCOPING_DONE],
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
        "task": inputs["task"],
        "rules_file": str(inputs["rules_file"]),
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

            workspace = inputs["runs_root"] / run_id
            question_round = client.get(
                f"/api/runs/{run_id}/artifacts/scoping_questions.json"
            ).json()
            assert question_round["round"] == 1

            # Round identity comes from structured workflow state, not from
            # counting editable Markdown headings. A stray heading after the
            # open placeholder must not turn this submission into round 2.
            answers_path = workspace / "artifacts/scoping_answers.md"
            answers_path.write_text(
                answers_path.read_text() + "\n## Round 98\n\nstale text\n"
            )

            resumed = client.post(
                f"/api/runs/{run_id}/resume",
                json={
                    "answers": {
                        "Q1": {"value": "One source folder."},
                        "Q2": {
                            "value": "fall",
                            "note": "Except beta, which spans both.",
                        },
                        "Q3": {"value": ["alpha", "beta"]},
                        "Q4": {"value": True},
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

## Round 1

### Q1

> What is one row?

One source folder.

### Q2

> Which period applies?

Fall

Note: Except beta, which spans both.

### Q3

> Which folders are authoritative?

- Alpha
- Beta

### Q4

> Is this set complete?

Yes
"""
    )
