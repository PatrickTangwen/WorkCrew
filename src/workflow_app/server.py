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
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from workflow_app.artifacts import (
    ArtifactCatalog,
    ArtifactNotFoundError,
    RunNotFoundError,
)
from workflow_app.audit.db import AuditStore
from workflow_app.progress import emit
from workflow_app.workflow.engine import new_run_id, run_workflow
from workflow_app.workspace import RunInputs

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8470
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"
RunStatus = Literal["running", "paused", "completed", "failed", "cancelled"]


class CreateRunRequest(BaseModel):
    source: str
    workbook: str
    rules: str
    workbook_schema: str
    scoping_answers: str | None = None
    review_policy: str | None = None


class RunRecord(BaseModel):
    run_id: str
    status: RunStatus
    start_time: str
    workspace_path: str
    phase: str
    source_name: str
    workbook_name: str


class RunSummary(BaseModel):
    run_id: str
    status: RunStatus
    started_at: str
    duration: float
    source_name: str
    workbook_name: str


@dataclass(frozen=True)
class RunFacts:
    run_id: str
    status: RunStatus
    started_at: str
    finished_at: str | None
    source_name: str
    workbook_name: str

    def summary(self):
        return RunSummary(
            run_id=self.run_id,
            status=self.status,
            started_at=self.started_at,
            duration=_duration(self.started_at, self.finished_at),
            source_name=self.source_name,
            workbook_name=self.workbook_name,
        ).model_dump()


@dataclass
class TrackedRun:
    record: RunRecord
    finished_at: str | None = None
    events: "RunEventChannel" = field(default_factory=lambda: RunEventChannel())


class RunEventChannel:
    terminal_types = frozenset({"completed", "failed"})

    def __init__(self):
        self.history = []
        self.subscribers = set()
        self.terminal = False

    def publish(self, event):
        if self.terminal:
            raise RuntimeError("Cannot publish after a terminal run event")
        self.history.append(event)
        for queue in self.subscribers:
            queue.put_nowait(event)
        if event["type"] in self.terminal_types:
            self.terminal = True

    def subscribe(self):
        queue = asyncio.Queue()
        for event in self.history:
            queue.put_nowait(event)
        if not self.terminal:
            self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)


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
        if any(
            run.record.status in {"running", "paused"} for run in self.runs.values()
        ):
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
        tracked = TrackedRun(record)
        self.runs[record.run_id] = tracked
        response = record.model_dump()
        loop = asyncio.get_running_loop()

        def progress_callback(event):
            loop.call_soon_threadsafe(self._receive_event, tracked, dict(event))

        task = asyncio.create_task(self._execute(tracked, inputs, progress_callback))
        self.tasks.add(task)
        task.add_done_callback(lambda done: self._finish(done, tracked))
        return response

    def find(self, run_id):
        tracked = self.runs.get(run_id)
        return None if tracked is None else tracked.record.model_dump()

    def subscribe(self, run_id):
        tracked = self.runs.get(run_id)
        return None if tracked is None else tracked.events.subscribe()

    def unsubscribe(self, run_id, queue):
        tracked = self.runs.get(run_id)
        if tracked is not None:
            tracked.events.unsubscribe(queue)

    def list_summaries(self):
        return [
            RunFacts(
                run_id=tracked.record.run_id,
                status=tracked.record.status,
                started_at=tracked.record.start_time,
                finished_at=tracked.finished_at,
                source_name=tracked.record.source_name,
                workbook_name=tracked.record.workbook_name,
            ).summary()
            for tracked in self.runs.values()
        ]

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

    async def _execute(self, tracked, inputs, progress_callback):
        record = tracked.record
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
            progress_callback=progress_callback,
        )

        record.phase = result.get("phase", record.phase)
        record.status = "paused" if "__interrupt__" in result else "completed"
        if record.status == "completed":
            tracked.finished_at = datetime.now(UTC).isoformat()

    def _finish(self, task, tracked):
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            record = tracked.record
            record.status = "failed"
            tracked.finished_at = datetime.now(UTC).isoformat()

    def _receive_event(self, tracked, event):
        record = tracked.record
        if event["type"] == "phase_change":
            record.phase = event["phase"]
        elif event["type"] == "paused":
            record.status = "paused"
        elif event["type"] == "completed":
            record.status = "completed"
            tracked.finished_at = datetime.now(UTC).isoformat()
        elif event["type"] == "failed":
            record.status = "failed"
            tracked.finished_at = datetime.now(UTC).isoformat()
        tracked.events.publish(event)


class RunHistory:
    def __init__(self, runs_root):
        self.runs_root = Path(runs_root)

    def list_summaries(self):
        if not self.runs_root.is_dir():
            return []

        summaries = [
            self._read_summary(audit_db)
            for audit_db in self.runs_root.glob("*/state/audit.sqlite")
        ]
        summaries.sort(key=lambda run: run["started_at"], reverse=True)
        return summaries

    def get_record(self, run_id):
        root = self.runs_root.resolve()
        workspace = (root / run_id).resolve()
        if not workspace.is_relative_to(root):
            raise HTTPException(status_code=404, detail="Run not found")
        run, stages = self._read_run(workspace)

        phase = stages[-1]["stage"] if stages else run["status"].upper()
        return RunRecord(
            run_id=run["run_id"],
            status=run["status"],
            start_time=run["started_at"],
            workspace_path=str(workspace),
            phase=phase,
            source_name=Path(run["source_path"]).name,
            workbook_name=Path(run["workbook_path"]).name,
        ).model_dump()

    def _read_summary(self, audit_db):
        run, _ = self._read_run(audit_db.parents[1])
        return RunFacts(
            run_id=run["run_id"],
            status=run["status"],
            started_at=run["started_at"],
            finished_at=run["finished_at"],
            source_name=Path(run["source_path"]).name,
            workbook_name=Path(run["workbook_path"]).name,
        ).summary()

    def _read_run(self, workspace):
        run_id = workspace.name
        audit_db = workspace / "state" / "audit.sqlite"
        if not audit_db.is_file():
            raise HTTPException(status_code=404, detail="Run not found")
        audit = AuditStore(audit_db)
        try:
            try:
                run = audit.get_run(run_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Run not found") from exc
            stages = audit.list_stages(run_id)
        finally:
            audit.close()
        return run, stages


def _duration(started_at, finished_at=None):
    started = datetime.fromisoformat(started_at)
    finished = (
        datetime.now(UTC)
        if finished_at is None
        else datetime.fromisoformat(finished_at)
    )
    return max(0.0, (finished - started).total_seconds())


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
    history = RunHistory(options.runs_root)
    artifacts = ArtifactCatalog(options.runs_root)
    browser = HomeBrowser(options.home_dir)

    @app.post("/api/runs", status_code=201)
    async def create_run(request: CreateRunRequest):
        return await coordinator.start(request)

    @app.get("/api/runs")
    async def list_runs():
        stored_runs = await asyncio.to_thread(history.list_summaries)
        runs_by_id = {run["run_id"]: run for run in stored_runs}
        runs_by_id.update({run["run_id"]: run for run in coordinator.list_summaries()})
        return sorted(
            runs_by_id.values(),
            key=lambda run: run["started_at"],
            reverse=True,
        )

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str):
        current = coordinator.find(run_id)
        if current is not None:
            return current
        return await asyncio.to_thread(history.get_record, run_id)

    @app.websocket("/ws/runs/{run_id}")
    async def stream_run(websocket: WebSocket, run_id: str):
        queue = coordinator.subscribe(run_id)
        if queue is None:
            await websocket.close(code=4404, reason="Run not found")
            return

        await websocket.accept()
        try:
            while True:
                event = await queue.get()
                await websocket.send_json(event)
                if event["type"] in RunEventChannel.terminal_types:
                    break
        except WebSocketDisconnect:
            pass
        finally:
            coordinator.unsubscribe(run_id, queue)

    @app.get("/api/runs/{run_id}/artifacts")
    def list_artifacts(run_id: str):
        try:
            return artifacts.list(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @app.get("/api/runs/{run_id}/artifacts/{name}")
    def get_artifact(run_id: str, name: str):
        try:
            artifact = artifacts.get(run_id, name)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ArtifactNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        filename = artifact.path.name if artifact.type == "xlsx" else None
        return FileResponse(
            artifact.path,
            media_type=artifact.media_type,
            filename=filename,
        )

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
