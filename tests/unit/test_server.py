import socket
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from workflow_app.server import ServerOptions, bind_available_socket, create_app


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
