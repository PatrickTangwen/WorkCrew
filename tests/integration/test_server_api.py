from fastapi.testclient import TestClient

from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.server import ServerOptions, create_app


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
