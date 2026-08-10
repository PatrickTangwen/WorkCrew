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
from pydantic import BaseModel, model_validator

from workflow_app.artifacts import (
    ArtifactCatalog,
    ArtifactNotFoundError,
    RunNotFoundError,
)
from workflow_app.audit.db import AuditStore
from workflow_app.cancellation import CancellationToken, WorkflowCancelled
from workflow_app.models import ScopingAnswer, ScopingQuestionRound
from workflow_app.native_picker import PickerUnavailable, pick_path
from workflow_app.progress import emit
from workflow_app.reports import (
    render_scoping_answers,
    replace_scoping_round,
)
from workflow_app.workflow.engine import new_run_id, resume_workflow, run_workflow
from workflow_app.workspace import RunInputs, Workspace, validate_task_and_rules

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8470
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"
RunStatus = Literal["running", "paused", "completed", "failed", "cancelled"]


class CreateRunRequest(BaseModel):
    source: str
    workbook: str
    task: str
    rules_text: str | None = None
    rules_file: str | None = None
    scoping_answers: str | None = None
    review_policy: str | None = None

    @model_validator(mode="after")
    def _usable_run_request(self):
        # RunInputs enforces these too, but only once the run is under
        # way; rejecting here turns a failed run into a 422.
        validate_task_and_rules(self.task, self.rules_text, self.rules_file)
        return self


class ResumeRunRequest(BaseModel):
    answers: dict[str, ScopingAnswer]


class PickPathRequest(BaseModel):
    mode: Literal["directory", "file"]
    prompt: str


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
    task: asyncio.Task | None = None
    cancellation: CancellationToken = field(default_factory=CancellationToken)


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
    resumer: Callable = resume_workflow
    picker: Callable = pick_path
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
            task=request.task,
            rules_text=request.rules_text,
            rules_file=None if request.rules_file is None else Path(request.rules_file),
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
        progress_callback = self._progress_callback(tracked)
        self._schedule(tracked, self._execute(tracked, inputs, progress_callback))
        return response

    async def resume(self, run_id, request):
        tracked = self.runs.get(run_id)
        if tracked is None:
            record = await asyncio.to_thread(
                RunHistory(self.options.runs_root).get_record, run_id
            )
            tracked = self.runs.setdefault(
                run_id,
                TrackedRun(RunRecord.model_validate(record)),
            )
        if any(
            candidate.record.run_id != run_id
            and candidate.record.status in {"running", "paused"}
            for candidate in self.runs.values()
        ):
            raise HTTPException(status_code=409, detail="A run is already active")
        resumable = {"paused", "failed", "cancelled"}
        if tracked.record.status not in resumable:
            raise HTTPException(status_code=409, detail="Run is not resumable")
        if tracked.task is not None:
            await tracked.task
        if tracked.record.status not in resumable:
            raise HTTPException(status_code=409, detail="Run is not resumable")

        status = tracked.record.status
        if status == "paused":
            workspace = Workspace((Path(self.options.runs_root) / run_id).resolve())
            questions = ScopingQuestionRound.model_validate_json(
                workspace.scoping_questions_json.read_text()
            )
            expected = {question.id for question in questions.questions}
            received = set(request.answers)
            if received != expected:
                missing = sorted(expected - received)
                unknown = sorted(received - expected)
                raise HTTPException(
                    status_code=422,
                    detail=f"Answers must match the scoping questions."
                    f" Missing: {missing}. Unknown: {unknown}.",
                )
            # The scoping pass appended a placeholder section for the
            # round it just asked; these answers take its place, leaving
            # earlier rounds intact for the next pass to read.
            replace_scoping_round(
                workspace.scoping_answers_md,
                questions.round,
                render_scoping_answers(questions, request.answers, questions.round),
            )

        if status in {"failed", "cancelled"}:
            tracked.events = RunEventChannel()
        tracked.cancellation = CancellationToken()
        tracked.record.status = "running"
        response = tracked.record.model_dump()
        progress_callback = self._progress_callback(tracked)
        self._schedule(tracked, self._resume(tracked, progress_callback))
        return response

    async def cancel(self, run_id):
        tracked = self.runs.get(run_id)
        if tracked is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if tracked.record.status != "running" or tracked.task is None:
            raise HTTPException(status_code=409, detail="Run is not running")

        task = tracked.task
        tracked.cancellation.cancel()
        await task
        return tracked.record.model_dump()

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
        await self._run_operation(
            tracked,
            self.options.runner,
            inputs=inputs,
            runs_root=Path(self.options.runs_root),
            runtimes=self._runtimes(),
            run_id=tracked.record.run_id,
            progress_callback=progress_callback,
            cancellation=tracked.cancellation,
        )

    async def _resume(self, tracked, progress_callback):
        await self._run_operation(
            tracked,
            self.options.resumer,
            run_id=tracked.record.run_id,
            runs_root=Path(self.options.runs_root),
            runtimes=self._runtimes(),
            progress_callback=progress_callback,
            cancellation=tracked.cancellation,
        )

    async def _run_operation(self, tracked, operation, **kwargs):
        try:
            result = await asyncio.to_thread(operation, **kwargs)
        except WorkflowCancelled:
            tracked.record.status = "cancelled"
            tracked.finished_at = datetime.now(UTC).isoformat()
            return
        self._record_result(tracked, result)

    def _record_result(self, tracked, result):
        record = tracked.record
        record.phase = result.get("phase", record.phase)
        record.status = "paused" if "__interrupt__" in result else "completed"
        if record.status == "completed":
            tracked.finished_at = datetime.now(UTC).isoformat()

    def _runtimes(self):
        if self.options.runtimes is not None:
            return self.options.runtimes
        from workflow_app.cli import build_runtimes

        return build_runtimes("live")

    def _progress_callback(self, tracked):
        loop = asyncio.get_running_loop()

        def callback(event):
            delivered = asyncio.run_coroutine_threadsafe(
                self._deliver_event(tracked, dict(event)), loop
            )
            delivered.result()

        return callback

    async def _deliver_event(self, tracked, event):
        self._receive_event(tracked, event)

    def _schedule(self, tracked, operation):
        task = asyncio.create_task(operation)
        tracked.task = task
        self.tasks.add(task)
        task.add_done_callback(lambda done: self._finish(done, tracked))

    def _finish(self, task, tracked):
        self.tasks.discard(task)
        if tracked.task is task:
            tracked.task = None
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
            record.status = (
                "cancelled" if event.get("reason") == "cancelled" else "failed"
            )
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

    @app.post("/api/runs", status_code=201)
    async def create_run(request: CreateRunRequest):
        return await coordinator.start(request)

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str, request: ResumeRunRequest):
        return await coordinator.resume(run_id, request)

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str):
        return await coordinator.cancel(run_id)

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

    @app.post("/api/pick")
    async def pick_input_path(request: PickPathRequest):
        try:
            path = await asyncio.to_thread(
                options.picker, request.mode, request.prompt, options.home_dir
            )
        except PickerUnavailable as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"path": path}

    if index.is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
    return app


def run_ui(starting_port=DEFAULT_UI_PORT):
    """Serve the built UI on loopback and open it in the default browser."""
    app = create_app(require_frontend=True)
    with bind_available_socket(starting_port=starting_port) as selected:
        host, port = selected.getsockname()
        url = f"http://{host}:{port}"
        emit(f"WorkCrew UI available at {url}")
        webbrowser.open_new_tab(url)

        config = uvicorn.Config(app, host=host, port=port)
        uvicorn.Server(config).run(sockets=[selected])
