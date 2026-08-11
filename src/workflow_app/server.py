"""Local web server for the WorkCrew browser UI."""

import asyncio
import base64
import binascii
import errno
import json
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

from workflow_app.agent_config import (
    agent_options,
    build_agent_config,
    read_agent_config,
)
from workflow_app.artifacts import (
    ArtifactCatalog,
    ArtifactNotFoundError,
    RunNotFoundError,
    resolve_run_workspace,
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
from workflow_app.workspace import (
    IMAGE_SUFFIXES,
    RunInputs,
    TaskImage,
    Workspace,
    validate_task_and_rules,
)

UI_HOST = "127.0.0.1"
DEFAULT_UI_PORT = 8470
DEFAULT_STATIC_DIR = Path(__file__).parent / "static"
RunStatus = Literal["running", "paused", "completed", "failed", "cancelled"]


class AgentSelection(BaseModel):
    model: str | None = None
    effort: str | None = None


# A pasted image has no file on the operator's disk, so it travels as
# content. The cap is generous for screenshots and small enough that a
# stray paste cannot exhaust the local server's memory.
MAX_TASK_IMAGE_BYTES = 12 * 1024 * 1024


class TaskImageUpload(BaseModel):
    content_type: str
    data: str  # base64

    def decoded(self):
        suffix = IMAGE_SUFFIXES.get(self.content_type)
        if suffix is None:
            raise ValueError(
                f"unsupported image type {self.content_type!r};"
                f" supported types are {sorted(IMAGE_SUFFIXES)}"
            )
        try:
            data = base64.b64decode(self.data, validate=True)
        except binascii.Error as exc:
            raise ValueError("task image is not valid base64") from exc
        return TaskImage(suffix=suffix, data=data)


class CreateRunRequest(BaseModel):
    source: str
    workbook: str
    task: str
    name: str | None = None
    # Per-role model and effort; an absent role keeps the default.
    agents: dict[str, AgentSelection] | None = None
    # Images pasted into the task description, in paste order.
    task_images: list[TaskImageUpload] = []
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
    # Null until the run stops. A finished run reports its own total time
    # rather than leaving the reader to guess from a stale summary.
    finished_at: str | None = None
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

    def restart(self):
        """Start a new attempt without dropping a paused run's subscribers."""
        self.history.clear()
        self.terminal = False


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
        self.event_log = RunEventLog(options.runs_root)

    async def start(self, request):
        if any(
            run.record.status in {"running", "paused"} for run in self.runs.values()
        ):
            raise HTTPException(status_code=409, detail="A run is already active")

        try:
            images = tuple(upload.decoded() for upload in request.task_images)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        total = sum(len(image.data) for image in images)
        if total > MAX_TASK_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"task images total {total} bytes;"
                f" the limit is {MAX_TASK_IMAGE_BYTES}",
            )

        inputs = RunInputs(
            source=Path(request.source),
            workbook=Path(request.workbook),
            task=request.task,
            name=request.name,
            task_images=images,
            rules_text=request.rules_text,
            rules_file=None if request.rules_file is None else Path(request.rules_file),
            scoping_answers=None
            if request.scoping_answers is None
            else Path(request.scoping_answers),
            review_policy=None
            if request.review_policy is None
            else Path(request.review_policy),
        )
        try:
            agents = build_agent_config(
                {
                    role: selection.model_dump()
                    for role, selection in (request.agents or {}).items()
                }
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            record = self._new_record(inputs)
        except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        tracked = TrackedRun(record)
        self.runs[record.run_id] = tracked
        response = record.model_dump()
        progress_callback = self._progress_callback(tracked)
        self._schedule(
            tracked, self._execute(tracked, inputs, agents, progress_callback)
        )
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
                questions.placeholder_token,
                render_scoping_answers(questions, request.answers, questions.round),
            )

        if status == "paused":
            tracked.events.restart()
        else:
            tracked.events = RunEventChannel()
        tracked.cancellation = CancellationToken()
        tracked.record.status = "running"
        # A run that is going again has not finished. Keeping the previous
        # ending would report the abandoned attempt's total as this one's.
        tracked.record.finished_at = None
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
                finished_at=tracked.record.finished_at,
                source_name=tracked.record.source_name,
                workbook_name=tracked.record.workbook_name,
            ).summary()
            for tracked in self.runs.values()
        ]

    def _new_record(self, inputs):
        runs_root = Path(self.options.runs_root)
        run_id = new_run_id(name=inputs.name, source=inputs.source, runs_root=runs_root)
        return RunRecord(
            run_id=run_id,
            status="running",
            start_time=datetime.now(UTC).isoformat(),
            workspace_path=str((runs_root / run_id).resolve()),
            phase="INITIALIZING",
            source_name=inputs.source.name,
            workbook_name=inputs.workbook.name,
        )

    async def _execute(self, tracked, inputs, agents, progress_callback):
        await self._run_operation(
            tracked,
            self.options.runner,
            inputs=inputs,
            runs_root=Path(self.options.runs_root),
            runtimes=self._runtimes(agents),
            run_id=tracked.record.run_id,
            workspace_reserved=True,
            agents=agents,
            progress_callback=progress_callback,
            cancellation=tracked.cancellation,
        )

    async def _resume(self, tracked, progress_callback):
        # A resume continues on the models the run started with; the
        # server has no way to ask again for a run it may not have
        # started (ADR 0036).
        agents = read_agent_config(
            Workspace(
                (Path(self.options.runs_root) / tracked.record.run_id).resolve()
            ).agents_json
        )
        await self._run_operation(
            tracked,
            self.options.resumer,
            run_id=tracked.record.run_id,
            runs_root=Path(self.options.runs_root),
            runtimes=self._runtimes(agents),
            progress_callback=progress_callback,
            cancellation=tracked.cancellation,
        )

    async def _run_operation(self, tracked, operation, **kwargs):
        try:
            result = await asyncio.to_thread(operation, **kwargs)
        except WorkflowCancelled:
            tracked.record.status = "cancelled"
            tracked.record.finished_at = datetime.now(UTC).isoformat()
            return
        self._record_result(tracked, result)

    def _record_result(self, tracked, result):
        record = tracked.record
        record.phase = result.get("phase", record.phase)
        record.status = "paused" if "__interrupt__" in result else "completed"
        if record.status == "completed":
            tracked.record.finished_at = datetime.now(UTC).isoformat()

    def _runtimes(self, agents):
        if self.options.runtimes is not None:
            return self.options.runtimes
        from workflow_app.cli import build_runtimes

        return build_runtimes("live", agents=agents)

    def _progress_callback(self, tracked):
        loop = asyncio.get_running_loop()

        def callback(event):
            # Written from the engine's own thread, before anyone is told
            # about the event: the log is what a reopened run replays, so
            # it must never trail the websocket.
            self.event_log.append(tracked.record.run_id, event)
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
            record.finished_at = datetime.now(UTC).isoformat()

    def _receive_event(self, tracked, event):
        record = tracked.record
        if event["type"] == "phase_change":
            record.phase = event["phase"]
        elif event["type"] == "paused":
            record.status = "paused"
        elif event["type"] == "completed":
            record.status = "completed"
            record.finished_at = datetime.now(UTC).isoformat()
        elif event["type"] == "failed":
            record.status = (
                "cancelled" if event.get("reason") == "cancelled" else "failed"
            )
            record.finished_at = datetime.now(UTC).isoformat()
        tracked.events.publish(event)


class RunEventLog:
    """One run's progress stream on disk, one JSON event per line.

    The websocket only reaches whoever is watching while the run happens.
    This is the copy a reopened run — after a reload, or after the server
    itself restarted — replays.

    Writing it is best effort. A run that cannot record its progress is
    still a run worth finishing, so a log that fails is abandoned rather
    than allowed to take the outputs down with it.
    """

    def __init__(self, runs_root):
        self.runs_root = Path(runs_root)
        self.abandoned = set()

    def append(self, run_id, event):
        if run_id in self.abandoned:
            return
        # The run is still being written, so its audit store may not exist
        # yet; the workspace directory is reserved before the engine starts.
        path = Workspace((self.runs_root / run_id).resolve()).events_jsonl
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event) + "\n")
        except OSError as exc:
            # Said once, then the log stays shut: a failing disk would
            # otherwise repeat this for every event left in the run.
            self.abandoned.add(run_id)
            emit(f"Run {run_id} progress log stopped ({exc}); the run continues")

    def read(self, run_id):
        path = Workspace(resolve_run_workspace(self.runs_root, run_id)).events_jsonl
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # An append-only log is whole up to its first damaged line;
                # a write cut short leaves the rest unreadable by definition.
                break
        return events


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
            finished_at=run["finished_at"],
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
    event_log = RunEventLog(options.runs_root)

    @app.get("/api/agents")
    async def list_agent_options():
        """What the operator may choose per role, and the defaults."""
        return agent_options()

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

    @app.get("/api/runs/{run_id}/events")
    def list_run_events(run_id: str):
        """The run's whole progress stream, however long ago it happened."""
        try:
            return event_log.read(run_id)
        except RunNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

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
