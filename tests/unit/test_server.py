import socket
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from workflow_app.audit.db import AuditStore
from workflow_app.server import ServerOptions, bind_available_socket, create_app
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


def run_payload(home):
    return {
        "source": str(home / "source"),
        "workbook": str(home / "template.xlsx"),
        "rules": str(home / "rules"),
        "workbook_schema": str(home / "workbook-schema.json"),
        "scoping_answers": None,
        "review_policy": None,
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
        rules=Path("/inputs/rules"),
        workbook_schema=Path("/inputs/workbook-schema.json"),
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


def test_browse_lists_home_directory_entries(tmp_path):
    home = tmp_path / "home"
    source = home / "source"
    source.mkdir(parents=True)
    workbook = home / "template.xlsx"
    workbook.write_bytes(b"workbook")
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=home),
        )
    )

    response = client.get("/api/browse")

    assert response.status_code == 200
    listing = response.json()
    assert listing["path"] == str(home)
    assert listing["root"] == str(home)
    assert [(entry["name"], entry["type"]) for entry in listing["entries"]] == [
        ("source", "directory"),
        ("template.xlsx", "file"),
    ]
    assert all(
        set(entry) == {"name", "type", "size", "modified"}
        for entry in listing["entries"]
    )


def test_browse_rejects_paths_outside_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    client = TestClient(
        create_app(
            tmp_path / "missing-static",
            options=ServerOptions(home_dir=home),
        )
    )

    response = client.get(
        "/api/browse",
        params={"path": str(Path(home) / ".." / outside.name)},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Path must stay within the home directory"}
