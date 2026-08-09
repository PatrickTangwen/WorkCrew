"""Local web server for the WorkCrew browser UI."""

import asyncio
import errno
import socket
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from workflow_app.progress import emit
from workflow_app.workflow.engine import new_run_id, run_workflow
from workflow_app.workspace import RunInputs

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8470
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


class CreateRunRequest(BaseModel):
    source: str
    workbook: str
    rules: str
    workbook_schema: str
    scoping_answers: str | None = None
    review_policy: str | None = None


class RunRecord(BaseModel):
    run_id: str
    status: Literal["running", "paused", "completed", "failed"]
    start_time: str
    workspace_path: str
    phase: str
    source_name: str
    workbook_name: str


@dataclass(frozen=True)
class ServerOptions:
    home_dir: Path = field(default_factory=Path.home)
    runs_root: Path = Path("runs")
    runner: Callable = run_workflow
    runtimes: dict | None = None


class RunCoordinator:
    def __init__(self, options):
        self.options = options
        self.runs = {}
        self.tasks = set()

    async def start(self, request):
        if any(run.status in {"running", "paused"} for run in self.runs.values()):
            raise HTTPException(status_code=409, detail="A run is already active")

        inputs = RunInputs(
            source=Path(request.source),
            workbook=Path(request.workbook),
            rules=Path(request.rules),
            workbook_schema=Path(request.workbook_schema),
            scoping_answers=None
            if request.scoping_answers is None
            else Path(request.scoping_answers),
            review_policy=None
            if request.review_policy is None
            else Path(request.review_policy),
        )
        record = self._new_record(inputs)
        self.runs[record.run_id] = record
        response = record.model_dump()
        task = asyncio.create_task(self._execute(record, inputs))
        self.tasks.add(task)
        task.add_done_callback(lambda done: self._finish(done, record))
        return response

    def get(self, run_id):
        try:
            return self.runs[run_id].model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    def _new_record(self, inputs):
        run_id = new_run_id()
        runs_root = Path(self.options.runs_root)
        return RunRecord(
            run_id=run_id,
            status="running",
            start_time=datetime.now(UTC).isoformat(),
            workspace_path=str((runs_root / run_id).resolve()),
            phase="INITIALIZING",
            source_name=inputs.source.name,
            workbook_name=inputs.workbook.name,
        )

    async def _execute(self, record, inputs):
        runtimes = self.options.runtimes
        if runtimes is None:
            from workflow_app.cli import build_runtimes

            runtimes = build_runtimes("live")
        result = await asyncio.to_thread(
            self.options.runner,
            inputs=inputs,
            runs_root=Path(self.options.runs_root),
            runtimes=runtimes,
            run_id=record.run_id,
        )

        record.phase = result.get("phase", record.phase)
        record.status = "paused" if "__interrupt__" in result else "completed"

    def _finish(self, task, record):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            record.status = "failed"
            record.phase = "FAILED"


class HomeBrowser:
    def __init__(self, home_dir):
        self.root = Path(home_dir).resolve()

    def list_directory(self, path=None):
        selected = self._resolve(path)
        if not selected.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        if not selected.is_dir():
            raise HTTPException(status_code=400, detail="Path must be a directory")

        entries = []
        for entry in selected.iterdir():
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )
        entries.sort(
            key=lambda entry: (
                entry["type"] != "directory",
                entry["name"].casefold(),
            )
        )
        return {"path": str(selected), "root": str(self.root), "entries": entries}

    def _resolve(self, path):
        if path is None or path == "~":
            selected = self.root
        elif path.startswith("~/"):
            selected = self.root / path[2:]
        else:
            selected = Path(path)
        selected = selected.resolve()
        if not selected.is_relative_to(self.root):
            raise HTTPException(
                status_code=403,
                detail="Path must stay within the home directory",
            )
        return selected


def bind_available_socket(host=UI_HOST, starting_port=DEFAULT_UI_PORT):
    """Reserve the first available TCP port at or above ``starting_port``."""
    for port in range(starting_port, 65536):
        selected = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        selected.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            selected.bind((host, port))
        except OSError as exc:
            selected.close()
            if exc.errno == errno.EADDRINUSE:
                continue
            raise
        selected.listen()
        return selected

    raise RuntimeError(f"No available port at or above {starting_port}")


def create_app(static_dir=DEFAULT_STATIC_DIR, require_frontend=False, options=None):
    """Create the FastAPI app, mounting the production frontend when present."""
    static_dir = Path(static_dir)
    options = options or ServerOptions()
    index = static_dir / "index.html"
    if require_frontend and not index.is_file():
        raise FileNotFoundError(
            f"Frontend build not found at {index}. Run `pnpm build` in frontend/."
        )

    app = FastAPI(title="WorkCrew")
    coordinator = RunCoordinator(options)
    browser = HomeBrowser(options.home_dir)

    @app.post("/api/runs", status_code=201)
    async def create_run(request: CreateRunRequest):
        return await coordinator.start(request)

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        return coordinator.get(run_id)

    @app.get("/api/browse")
    def browse(path: str | None = None):
        return browser.list_directory(path)

    if index.is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


def run_ui():
    """Serve the built UI on loopback and open it in the default browser."""
    app = create_app(require_frontend=True)
    with bind_available_socket() as selected:
        host, port = selected.getsockname()
        url = f"http://{host}:{port}"
        emit(f"WorkCrew UI available at {url}")
        webbrowser.open_new_tab(url)

        config = uvicorn.Config(app, host=host, port=port)
        uvicorn.Server(config).run(sockets=[selected])
