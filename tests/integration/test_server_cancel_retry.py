import threading

from fastapi.testclient import TestClient

from tests.integration.conftest import WORKBOOK_SCHEMA_CONFIG
from workflow_app.audit.db import AuditStore
from workflow_app.runtimes.base import AgentResult
from workflow_app.server import ServerOptions, create_app
from workflow_app.workspace import Workspace

SCOPING_OUTPUT = {
    "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
    "questions": [{"id": "Q1", "question": "Is each folder one project?"}],
}


class BlockingThenSuccessfulRuntime:
    name = "blocking-fake"

    def __init__(self):
        self.filler_calls = 0
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.release_without_cancellation = threading.Event()

    def run(self, request):
        if request.role == "scoping":
            return AgentResult(status="ok", output=SCOPING_OUTPUT)
        if request.role == "filler":
            self.filler_calls += 1
            if self.filler_calls == 1:
                self.started.set()
                cancellation = getattr(request, "cancellation", None)
                try:
                    if cancellation is None:
                        self.release_without_cancellation.wait(timeout=1)
                    else:
                        cancellation.wait()
                        cancellation.raise_if_cancelled()
                finally:
                    self.stopped.set()
            return AgentResult(status="ok", output={"proposals": []})
        if request.role == "reviewer":
            return AgentResult(status="ok", output={"findings": []})
        raise AssertionError(f"Unexpected role: {request.role}")


class AlwaysFailRuntime:
    name = "failing-fake"

    def run(self, request):
        if request.role == "scoping":
            return AgentResult(status="ok", output=SCOPING_OUTPUT)
        if request.role == "filler":
            return AgentResult(status="error", error="temporary agent failure")
        raise AssertionError(f"Unexpected role: {request.role}")


class SuccessfulRuntime:
    name = "successful-fake"

    def run(self, request):
        outputs = {
            "scoping": SCOPING_OUTPUT,
            "filler": {"proposals": []},
            "reviewer": {"findings": []},
        }
        return AgentResult(status="ok", output=outputs[request.role])


def run_payload(inputs):
    return {
        "source": str(inputs["source"]),
        "workbook": str(inputs["workbook"]),
        "task": inputs["task"],
        "rules_file": str(inputs["rules_file"]),
        "scoping_answers": str(inputs["scoping_answers"]),
        "review_policy": None,
    }


def read_until_terminal(websocket):
    events = []
    while not events or events[-1]["type"] not in {"completed", "failed"}:
        events.append(websocket.receive_json())
    return events


def audit_status(runs_root, run_id):
    audit = AuditStore(Workspace(runs_root / run_id).audit_db)
    try:
        return audit.get_run(run_id)["status"]
    finally:
        audit.close()


def test_cancel_stops_the_engine_records_audit_and_clears_the_single_run_guard(inputs):
    runtime = BlockingThenSuccessfulRuntime()
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        ),
    )

    with TestClient(app) as client:
        created = client.post("/api/runs", json=run_payload(inputs)).json()
        assert runtime.started.wait(timeout=1)

        with client.websocket_connect(f"/ws/runs/{created['run_id']}") as websocket:
            cancelled = client.post(f"/api/runs/{created['run_id']}/cancel")
            events = read_until_terminal(websocket)

        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert runtime.stopped.is_set()
        assert audit_status(inputs["runs_root"], created["run_id"]) == "cancelled"
        assert events[-1]["type"] == "failed"
        assert events[-1]["reason"] == "cancelled"

        next_run = client.post("/api/runs", json=run_payload(inputs))
        assert next_run.status_code == 201
        with client.websocket_connect(
            f"/ws/runs/{next_run.json()['run_id']}"
        ) as websocket:
            assert read_until_terminal(websocket)[-1]["type"] == "completed"


def test_retry_resumes_a_cancelled_run_from_its_checkpoint(inputs):
    runtime = BlockingThenSuccessfulRuntime()
    app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        ),
    )

    with TestClient(app) as client:
        created = client.post("/api/runs", json=run_payload(inputs)).json()
        assert runtime.started.wait(timeout=1)
        assert client.post(f"/api/runs/{created['run_id']}/cancel").status_code == 200

        retried = client.post(
            f"/api/runs/{created['run_id']}/resume",
            json={"answers": {}},
        )

        assert retried.status_code == 202
        assert retried.json()["status"] == "running"
        with client.websocket_connect(f"/ws/runs/{created['run_id']}") as websocket:
            events = read_until_terminal(websocket)

        assert events[-1]["type"] == "completed"
        assert (
            client.get(f"/api/runs/{created['run_id']}").json()["status"] == "completed"
        )
        assert runtime.filler_calls == 2
        assert audit_status(inputs["runs_root"], created["run_id"]) == "completed"


def test_retry_loads_a_failed_historical_run_and_resumes_its_checkpoint(inputs):
    first_app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={
                "scoping": AlwaysFailRuntime(),
                "filler": AlwaysFailRuntime(),
            },
        ),
    )
    with TestClient(first_app) as client:
        created = client.post("/api/runs", json=run_payload(inputs)).json()
        with client.websocket_connect(f"/ws/runs/{created['run_id']}") as websocket:
            assert read_until_terminal(websocket)[-1]["type"] == "failed"
    assert audit_status(inputs["runs_root"], created["run_id"]) == "failed"

    runtime = SuccessfulRuntime()
    restarted_app = create_app(
        inputs["runs_root"] / "missing-static",
        options=ServerOptions(
            home_dir=inputs["source"].parent,
            runs_root=inputs["runs_root"],
            runtimes={"scoping": runtime, "filler": runtime, "reviewer": runtime},
        ),
    )
    with TestClient(restarted_app) as client:
        retried = client.post(
            f"/api/runs/{created['run_id']}/resume",
            json={"answers": {}},
        )
        assert retried.status_code == 202
        assert retried.json()["status"] == "running"
        with client.websocket_connect(f"/ws/runs/{created['run_id']}") as websocket:
            assert read_until_terminal(websocket)[-1]["type"] == "completed"

    assert audit_status(inputs["runs_root"], created["run_id"]) == "completed"
