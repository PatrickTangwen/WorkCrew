import asyncio
import socket
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from workflow_app import server
from workflow_app.audit.db import AuditStore
from workflow_app.native_picker import PickerUnavailable
from workflow_app.server import (
    ResumeRunRequest,
    RunCoordinator,
    RunRecord,
    ServerOptions,
    TrackedRun,
    bind_available_socket,
    create_app,
)
from workflow_app.workspace import RunInputs, Workspace


class BlockingRunner:
    def __init__(self):
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        self.release.wait(timeout=5)
        return {"phase": "PREPARE_WORKSPACE"}


class TwoResumeWaiters:
    def __init__(self):
        self.count = 0
        self.ready = None

    def __await__(self):
        async def wait():
            if self.ready is None:
                self.ready = asyncio.Event()
            self.count += 1
            if self.count == 2:
                self.ready.set()
            await self.ready.wait()

        return wait().__await__()


def run_payload(home):
    return {
        "source": str(home / "source"),
        "workbook": str(home / "template.xlsx"),
        "task": "Fill the register from the briefs.",
        "rules_text": None,
        "rules_file": None,
    }


@dataclass(frozen=True)
class HistoricalRun:
    run_id: str
    status: str
    started_at: str
    finished_at: str
    source_name: str
    workbook_name: str


def record_historical_run(runs_root, run):
    workspace = Workspace(runs_root / run.run_id)
    workspace.create_layout()
    inputs = RunInputs(
        source=Path("/inputs") / run.source_name,
        workbook=Path("/inputs") / run.workbook_name,
        task="Fill the register from the briefs.",
    )
    audit = AuditStore(workspace.audit_db)
    audit.record_run_started(run.run_id, inputs)
    audit.close()
    with sqlite3.connect(workspace.audit_db) as conn:
        conn.execute(
            "UPDATE runs SET status = ?, started_at = ?, finished_at = ?"
            " WHERE run_id = ?",
            (run.status, run.started_at, run.finished_at, run.run_id),
        )


def test_bind_available_socket_increments_past_an_occupied_port():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        starting_port = occupied.getsockname()[1]

        with bind_available_socket("127.0.0.1", starting_port) as selected:
            selected_host, selected_port = selected.getsockname()

    assert selected_host == "127.0.0.1"
    assert selected_port > starting_port


def test_run_ui_starts_from_the_requested_port(monkeypatch):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        requested_port = probe.getsockname()[1]

    opened = []
    served = []
    monkeypatch.setattr(server.webbrowser, "open_new_tab", opened.append)
    monkeypatch.setattr(
        server.uvicorn.Server,
        "run",
        lambda self, sockets: served.append(
            (self.config.port, sockets[0].getsockname())
        ),
    )

    server.run_ui(requested_port)

    expected_address = ("127.0.0.1", requested_port)
    assert opened == [f"http://127.0.0.1:{requested_port}"]
    assert served == [(requested_port, expected_address)]


def test_create_app_serves_the_built_spa(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<main id="root">WorkCrew UI is ready</main>'
    )
    (assets_dir / "app.js").write_text("console.log('ready')")

    client = TestClient(create_app(static_dir))

    page = client.get("/")
    asset = client.get("/assets/app.js")
    assert page.status_code == 200
    assert "WorkCrew UI is ready" in page.text
    assert asset.status_code == 200
    assert asset.text == "console.log('ready')"


def test_create_app_starts_without_a_production_frontend(tmp_path):
    client = TestClient(create_app(tmp_path / "missing-static"))

    response = client.get("/")

    assert response.status_code == 404


def test_post_run_starts_workflow_and_get_returns_status(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    runner = BlockingRunner()
    app = create_app(
        tmp_path / "missing-static",
        options=ServerOptions(
            home_dir=home,
            runs_root=tmp_path / "runs",
            runner=runner,
            runtimes={"fake": object()},
        ),
    )

    with TestClient(app) as client:
        created = client.post("/api/runs", json=run_payload(home))
        assert runner.started.wait(timeout=1)

        assert created.status_code == 201
        created_run = created.json()
        assert created_run["status"] == "running"
        assert created_run["phase"] == "INITIALIZING"
        assert created_run["source_name"] == "source"
        assert created_run["workbook_name"] == "template.xlsx"

        found = client.get(f"/api/runs/{created_run['run_id']}")
        assert found.status_code == 200
        assert found.json() == created_run
        call = runner.calls[0]
        assert call["run_id"] == created_run["run_id"]
        assert call["inputs"].source == home / "source"
        assert call["runs_root"] == tmp_path / "runs"

        runner.release.set()


def test_post_run_rejects_a_second_active_run(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    runner = BlockingRunner()
    app = create_app(
        tmp_path / "missing-static",
        options=ServerOptions(
            home_dir=home,
            runs_root=tmp_path / "runs",
            runner=runner,
            runtimes={},
        ),
    )

    with TestClient(app) as client:
        first = client.post("/api/runs", json=run_payload(home))
        assert runner.started.wait(timeout=1)

        second = client.post("/api/runs", json=run_payload(home))

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json() == {"detail": "A run is already active"}
        runner.release.set()


def test_concurrent_resume_requests_claim_a_paused_run_once(tmp_path):
    async def exercise():
        runs_root = tmp_path / "runs"
        workspace = Workspace(runs_root / "run-paused")
        workspace.create_layout()
        workspace.scoping_questions_json.write_text(
            '{"questions":[{"id":"Q1","question":"What is one row?"}]}'
        )
        resumer_calls = []

        def resumer(**kwargs):
            resumer_calls.append(kwargs)
            return {"phase": "FINALIZE"}

        coordinator = RunCoordinator(
            ServerOptions(runs_root=runs_root, resumer=resumer, runtimes={})
        )
        tracked = TrackedRun(
            RunRecord(
                run_id="run-paused",
                status="paused",
                start_time="2026-08-09T12:00:00+00:00",
                workspace_path=str(workspace.root),
                phase="CLAUDE_SCOPE",
                source_name="source",
                workbook_name="template.xlsx",
            ),
            task=TwoResumeWaiters(),
        )
        coordinator.runs[tracked.record.run_id] = tracked
        request = ResumeRunRequest(answers={"Q1": "One source file."})

        results = await asyncio.gather(
            coordinator.resume(tracked.record.run_id, request),
            coordinator.resume(tracked.record.run_id, request),
            return_exceptions=True,
        )
        if coordinator.tasks:
            await asyncio.gather(*coordinator.tasks)
        return results, resumer_calls

    results, resumer_calls = asyncio.run(exercise())

    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [
        result for result in results if getattr(result, "status_code", None) == 409
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert len(resumer_calls) == 1


def test_get_runs_lists_audit_history_newest_first(tmp_path):
    runs_root = tmp_path / "runs"
    record_historical_run(
        runs_root,
        HistoricalRun(
            run_id="run-older",
            status="completed",
            started_at="2026-08-08T10:00:00+00:00",
            finished_at="2026-08-08T10:01:30+00:00",
            source_name="older-source",
            workbook_name="older.xlsx",
        ),
    )
    record_historical_run(
        runs_root,
        HistoricalRun(
            run_id="run-newer",
            status="failed",
            started_at="2026-08-09T12:00:00+00:00",
            finished_at="2026-08-09T12:00:04+00:00",
            source_name="newer-source",
            workbook_name="newer.xlsx",
        ),
    )
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(runs_root=runs_root),
        )
    )

    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.json() == [
        {
            "run_id": "run-newer",
            "status": "failed",
            "started_at": "2026-08-09T12:00:00+00:00",
            "duration": 4.0,
            "source_name": "newer-source",
            "workbook_name": "newer.xlsx",
        },
        {
            "run_id": "run-older",
            "status": "completed",
            "started_at": "2026-08-08T10:00:00+00:00",
            "duration": 90.0,
            "source_name": "older-source",
            "workbook_name": "older.xlsx",
        },
    ]


def test_get_runs_includes_active_run_before_audit_record_exists(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    runs_root = tmp_path / "runs"
    record_historical_run(
        runs_root,
        HistoricalRun(
            run_id="run-historical",
            status="completed",
            started_at="2026-08-08T10:00:00+00:00",
            finished_at="2026-08-08T10:00:08+00:00",
            source_name="history-source",
            workbook_name="history.xlsx",
        ),
    )
    runner = BlockingRunner()
    app = create_app(
        tmp_path / "missing-static",
        options=ServerOptions(
            home_dir=home,
            runs_root=runs_root,
            runner=runner,
            runtimes={},
        ),
    )

    with TestClient(app) as client:
        try:
            created = client.post("/api/runs", json=run_payload(home)).json()
            assert runner.started.wait(timeout=1)

            runs = client.get("/api/runs").json()

            assert [run["run_id"] for run in runs] == [
                created["run_id"],
                "run-historical",
            ]
            assert runs[0]["status"] == "running"
            assert runs[0]["duration"] >= 0
            assert runs[0]["source_name"] == "source"
            assert runs[0]["workbook_name"] == "template.xlsx"
        finally:
            runner.release.set()


def test_get_runs_freezes_duration_when_current_run_finishes(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    app = create_app(
        tmp_path / "missing-static",
        options=ServerOptions(
            home_dir=home,
            runs_root=tmp_path / "runs",
            runner=lambda **_kwargs: {"phase": "FINALIZE"},
            runtimes={},
        ),
    )

    with TestClient(app) as client:
        created = client.post("/api/runs", json=run_payload(home)).json()
        for _ in range(100):
            if (
                client.get(f"/api/runs/{created['run_id']}").json()["status"]
                == "completed"
            ):
                break
            time.sleep(0.001)

        first_duration = client.get("/api/runs").json()[0]["duration"]
        time.sleep(0.02)
        second_duration = client.get("/api/runs").json()[0]["duration"]

    assert second_duration == first_duration


def test_get_historical_run_reads_detail_from_audit_store(tmp_path):
    runs_root = tmp_path / "runs"
    run_id = "run-completed"
    record_historical_run(
        runs_root,
        HistoricalRun(
            run_id=run_id,
            status="completed",
            started_at="2026-08-09T12:00:00+00:00",
            finished_at="2026-08-09T12:00:45+00:00",
            source_name="source-documents",
            workbook_name="delivery.xlsx",
        ),
    )
    workspace = Workspace(runs_root / run_id)
    audit = AuditStore(workspace.audit_db)
    audit.record_stage_started(run_id, "FINALIZE")
    audit.record_stage_finished(run_id, "FINALIZE")
    audit.close()
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(runs_root=runs_root),
        )
    )

    response = client.get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_id,
        "status": "completed",
        "start_time": "2026-08-09T12:00:00+00:00",
        "workspace_path": str(workspace.root.resolve()),
        "phase": "FINALIZE",
        "source_name": "source-documents",
        "workbook_name": "delivery.xlsx",
    }


def test_pick_opens_native_chooser_and_returns_the_path(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    calls = []

    def picker(mode, prompt, default_location):
        calls.append((mode, prompt, default_location))
        return str(home / "source")

    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=home, picker=picker),
        )
    )

    response = client.post(
        "/api/pick",
        json={"mode": "directory", "prompt": "Choose source folder"},
    )

    assert response.status_code == 200
    assert response.json() == {"path": str(home / "source")}
    assert calls == [("directory", "Choose source folder", home)]


def test_pick_reports_a_cancelled_chooser_as_no_path(tmp_path):
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=tmp_path, picker=lambda *_: None),
        )
    )

    response = client.post(
        "/api/pick", json={"mode": "file", "prompt": "Choose workbook"}
    )

    assert response.status_code == 200
    assert response.json() == {"path": None}


def test_pick_surfaces_an_unavailable_chooser(tmp_path):
    def picker(*_):
        raise PickerUnavailable("no display available")

    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=tmp_path, picker=picker),
        )
    )

    response = client.post(
        "/api/pick", json={"mode": "file", "prompt": "Choose workbook"}
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "no display available"}


def test_pick_rejects_an_unknown_mode(tmp_path):
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=tmp_path, picker=lambda *_: None),
        )
    )

    response = client.post("/api/pick", json={"mode": "drive", "prompt": "Choose"})

    assert response.status_code == 422
