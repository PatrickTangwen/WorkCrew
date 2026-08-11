import base64
import json

from fastapi.testclient import TestClient

from tests.integration.conftest import WORKBOOK_SCHEMA_CONFIG, scoping_fixture
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app

SCOPING_DONE = {"workbook_schema": WORKBOOK_SCHEMA_CONFIG, "questions": []}

SECOND_ROUND = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
    "questions": [{"id": "Q5", "question": "Which mapping applies?", "type": "text"}],
}

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


def test_run_api_rejects_a_runs_root_inside_the_source_before_writing(inputs):
    nested_runs_root = inputs["source"] / "runs"
    app = create_app(
        inputs["source"].parent / "missing-static",
        options=ServerOptions(runs_root=nested_runs_root),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "rules_file": str(inputs["rules_file"]),
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/runs", json=payload)

    assert response.status_code == 422
    assert not nested_runs_root.exists()


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


def test_a_new_socket_after_resume_does_not_replay_the_stale_pause(inputs):
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
        run_id = client.post("/api/runs", json=payload).json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            first_attempt = []
            while not first_attempt or first_attempt[-1]["type"] != "paused":
                first_attempt.append(websocket.receive_json())

        resumed = client.post(
            f"/api/runs/{run_id}/resume",
            json={
                "answers": {
                    "Q1": {"value": "One source folder."},
                    "Q2": {"value": "fall"},
                    "Q3": {"value": ["alpha", "beta"]},
                    "Q4": {"value": True},
                }
            },
        )
        assert resumed.status_code == 202
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            resumed_events = []
            while not resumed_events or resumed_events[-1]["type"] != "completed":
                resumed_events.append(websocket.receive_json())

    assert all(event["type"] != "paused" for event in resumed_events)


def test_a_note_that_looks_like_the_next_heading_does_not_block_resume(inputs):
    runtime = FakeAgentRuntime(
        {
            "scoping": [SCOPING_OUTPUT, SECOND_ROUND, SCOPING_DONE],
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

            first = client.post(
                f"/api/runs/{run_id}/resume",
                json={
                    "answers": {
                        "Q1": {"value": "One source folder."},
                        "Q2": {
                            "value": "fall",
                            "note": "Context\n## Round 2\nThis is still free prose.",
                        },
                        "Q3": {"value": ["alpha", "beta"]},
                        "Q4": {"value": True},
                    }
                },
            )
            assert first.status_code == 202
            events.append(websocket.receive_json())
            while events[-1]["type"] != "paused":
                events.append(websocket.receive_json())

            question_round = client.get(
                f"/api/runs/{run_id}/artifacts/scoping_questions.json"
            ).json()
            assert question_round["round"] == 2
            second = client.post(
                f"/api/runs/{run_id}/resume",
                json={"answers": {"Q5": {"value": "Use the broader mapping."}}},
            )
            assert second.status_code == 202
            events.append(websocket.receive_json())
            while events[-1]["type"] != "completed":
                events.append(websocket.receive_json())

    answers = (
        inputs["runs_root"] / run_id / "artifacts/scoping_answers.md"
    ).read_text()
    assert "## Round 2\nThis is still free prose." in answers
    assert "Use the broader mapping." in answers


def test_agent_options_describe_the_choices_the_form_offers(inputs):
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent, runs_root=inputs["runs_root"]
        ),
    )

    with TestClient(app) as client:
        options = client.get("/api/agents").json()

    by_role = {entry["role"]: entry for entry in options}
    assert set(by_role) == {"scoping", "filler", "revision", "reviewer", "re_review"}
    assert by_role["filler"]["runtime"] == "claude"
    assert by_role["reviewer"]["effort"] == "high"
    assert "ultra" in by_role["reviewer"]["effort_choices"]


def test_a_run_records_the_agent_choices_it_was_started_with(inputs):
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
        "agents": {"filler": {"model": "claude-sonnet-5", "effort": "max"}},
    }

    with TestClient(app) as client:
        created = client.post("/api/runs", json=payload)
        run_id = created.json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            events = []
            while not events or events[-1]["type"] != "completed":
                events.append(websocket.receive_json())

    # Recorded with the inputs, so a resume in a later process runs the
    # same models (ADR 0036).
    recorded = json.loads(
        (inputs["runs_root"] / run_id / "input" / "agents.json").read_text()
    )
    assert recorded["filler"] == {"model": "claude-sonnet-5", "effort": "max"}
    assert recorded["reviewer"] == {"model": "gpt-5.6-sol", "effort": "high"}


def test_a_mistyped_agent_choice_is_rejected_with_422(inputs):
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent, runs_root=inputs["runs_root"]
        ),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "agents": {"filler": {"effort": "ultra"}},
    }

    with TestClient(app) as client:
        response = client.post("/api/runs", json=payload)

    assert response.status_code == 422
    assert "unknown effort" in response.json()["detail"]


def test_pasted_images_reach_the_workspace_and_the_task(inputs):
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
        "task_images": [
            {
                "content_type": "image/png",
                "data": base64.b64encode(b"\x89PNG fake").decode(),
            }
        ],
    }

    with TestClient(app) as client:
        created = client.post("/api/runs", json=payload)
        run_id = created.json()["run_id"]
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            events = []
            while not events or events[-1]["type"] != "completed":
                events.append(websocket.receive_json())

    workspace = inputs["runs_root"] / run_id
    image = workspace / "input" / "task_images" / "task-image-1.png"
    assert image.read_bytes() == b"\x89PNG fake"
    # Named in the task the agents read, not just dropped on disk.
    assert (
        "input/task_images/task-image-1.png"
        in (workspace / "input" / "task.md").read_text()
    )


def test_an_unsupported_pasted_type_is_rejected(inputs):
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent, runs_root=inputs["runs_root"]
        ),
    )
    payload = {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "task_images": [
            {"content_type": "image/tiff", "data": base64.b64encode(b"x").decode()}
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/runs", json=payload)

    assert response.status_code == 422
    assert "unsupported image type" in response.json()["detail"]
