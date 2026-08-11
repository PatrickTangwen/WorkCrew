"""Workflow engine entries: start a run, resume a paused one.

This is the primary test seam: callers inject agent runtimes (fake in
tests and during fake-first development, live adapters later). Graph
state persists through a SqliteSaver checkpoint database inside the
run's state/ directory (plan section 30), keyed by run id.
"""

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from workflow_app.agent_config import default_agent_config, write_agent_config
from workflow_app.audit.db import AuditStore
from workflow_app.cancellation import CancellationToken, WorkflowCancelled
from workflow_app.progress import ProgressReporter
from workflow_app.review_policy import load_review_policy
from workflow_app.workflow.graph import build_graph
from workflow_app.workspace import RunInputs, Workspace

SLUG_MAX = 48


def slugify(text):
    """ASCII slug for a run id.

    A run id is a directory name, a URL segment, and a SQLite key at
    once, so it stays ASCII: a Unicode id would have to survive
    filesystem normalization (NFC/NFD) and URL encoding intact on every
    path it travels. Text with nothing to slugify yields "".
    """
    if text is None:
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return slug[:SLUG_MAX].strip("-")


def new_run_id(name=None, source=None, runs_root=None):
    """Claim a readable, unique run id: <name-or-source-folder>-<MMDD-HHMM>.

    The operator's run name leads when they gave one; otherwise the
    source folder names the run. Both can slugify to nothing (a name
    written entirely in non-Latin script, say), which is what the
    generic stem covers.
    """
    stem = (
        slugify(name)
        or slugify(Path(source).name if source is not None else "")
        or "run"
    )
    base = f"{stem}-{time.strftime('%m%d-%H%M')}"
    if runs_root is None:
        return base
    source, root = _claim_roots(source, runs_root)
    root.mkdir(parents=True, exist_ok=True)
    candidate, attempt = base, 2
    while True:
        if _claim_workspace(candidate, source, root) is None:
            candidate = f"{base}-{attempt}"
            attempt += 1
            continue
        return candidate


def _claim_roots(source, runs_root):
    """Resolve and validate both roots before a claim writes either one."""
    if source is None:
        raise ValueError("source is required when claiming a run id")
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise NotADirectoryError(f"source folder not found: {source}")
    runs_root = Path(runs_root).resolve()
    if runs_root.is_relative_to(source):
        raise ValueError(
            f"the runs root {runs_root} would sit inside the source folder"
            f" {source}, so copying the sources would recurse."
            " Choose a runs root outside the source folder."
        )
    return source, runs_root


def _claim_workspace(run_id, source, runs_root):
    """Atomically claim both identities, or return None without a claim."""
    workspace = Workspace((runs_root / run_id).resolve())
    try:
        workspace.root.mkdir()
    except FileExistsError:
        return None
    try:
        workspace.reserve_export(source, run_id)
    except FileExistsError:
        workspace.root.rmdir()
        return None
    except BaseException:
        workspace.root.rmdir()
        raise
    return workspace


@dataclass(frozen=True)
class WorkflowExecution:
    workspace: Workspace
    inputs: RunInputs
    runtimes: dict
    runs_root: Path
    run_id: str
    progress: ProgressReporter
    cancellation: CancellationToken


def run_workflow(
    inputs,
    runs_root,
    runtimes,
    *,
    run_id=None,
    workspace_reserved=False,
    agents=None,
    progress_callback=None,
    cancellation=None,
):
    progress = ProgressReporter(progress_callback)
    cancellation = cancellation or CancellationToken()
    try:
        inputs.validate()
        inputs = inputs.resolved()
        _, runs_root = _claim_roots(inputs.source, runs_root)
        # Fail fast on a malformed review policy — before the workspace
        # exists (tickets #3, #11). The schema is no longer checkable here:
        # the scoping pass derives it (ADR 0032), so its own validation and
        # the strict-fields cross-check moved into the LOAD_SCHEMA node.
        load_review_policy(inputs.review_policy)

        generated_run_id = run_id is None
        if generated_run_id:
            run_id = new_run_id(
                name=inputs.name, source=inputs.source, runs_root=runs_root
            )
        # Resolved so the paths persisted into checkpointed state stay valid
        # when the run is resumed from a different working directory.
        workspace = Workspace((runs_root / run_id).resolve())
        # A workspace inside the source folder makes copy_inputs copy the
        # sources into their own subdirectory, recursing until the OS
        # refuses the path length. Caught here, before anything is written.
        if workspace.root.is_relative_to(inputs.source.resolve()):
            raise ValueError(
                f"the run workspace {workspace.root} would sit inside the source"
                f" folder {inputs.source}, so copying the sources would recurse."
                " Choose a runs root outside the source folder."
            )
        if generated_run_id or workspace_reserved:
            if not workspace.root.is_dir():
                raise FileNotFoundError(
                    f"reserved run workspace is missing: {workspace.root}"
                )
        else:
            runs_root.mkdir(parents=True, exist_ok=True)
            claimed = _claim_workspace(run_id, inputs.source, runs_root)
            if claimed is None:
                raise FileExistsError(
                    f"run id or deliverable export is already in use: {run_id}"
                )
        workspace.create_layout()
        # Recorded with the run's inputs: which model and effort each
        # role ran on is part of what produced these results, and a
        # resume in a later process reads it back.
        write_agent_config(workspace.agents_json, agents or default_agent_config())
        progress.emit(f"Starting run {run_id}...")
        execution = WorkflowExecution(
            workspace=workspace,
            inputs=inputs,
            runtimes=runtimes,
            runs_root=runs_root,
            run_id=run_id,
            progress=progress,
            cancellation=cancellation,
        )
        initial_state = {
            "run_id": run_id,
            "workspace_path": str(workspace.root),
            "manifest_path": None,
            "workbook_outline_path": None,
            "schema_path": None,
            "scoping_questions_path": None,
            "scoping_round": 0,
            "scoping_pending": False,
            "scoping_answers_path": None,
            "extraction_path": None,
            "draft_xlsx_path": None,
            "review_path": None,
            "revision_path": None,
            "re_review_path": None,
            "phase": "",
        }
        return _invoke(execution, initial_state)
    except WorkflowCancelled:
        progress.cancelled()
        raise
    except BaseException as exc:
        progress.failed(exc)
        raise


def resume_workflow(
    run_id, runs_root, runtimes, *, progress_callback=None, cancellation=None
):
    progress = ProgressReporter(progress_callback)
    cancellation = cancellation or CancellationToken()
    try:
        workspace = Workspace((Path(runs_root) / run_id).resolve())
        if not workspace.root.is_dir():
            raise FileNotFoundError(
                f"no run workspace for run id {run_id!r} under {runs_root}"
            )
        if not workspace.audit_db.is_file():
            raise FileNotFoundError(
                f"run {run_id!r} has no audit store; it cannot be resumed"
            )

        audit = AuditStore(workspace.audit_db)
        try:
            try:
                run = audit.get_run(run_id)
            except KeyError as exc:
                raise FileNotFoundError(
                    f"run {run_id!r} has no recorded start; it cannot be resumed"
                ) from exc
            if run["status"] == "completed":
                raise ValueError(f"run {run_id!r} already completed; nothing to resume")
            if run["task"] is None:
                raise ValueError(
                    f"run {run_id!r} predates agent-derived workbook schemas"
                    " and cannot be resumed"
                )
            if not workspace.checkpoint_db.is_file():
                raise FileNotFoundError(f"run {run_id!r} has no resumable checkpoint")
            # The pause is over once resumption starts; FINALIZE records the
            # terminal status.
            audit.record_run_status(run_id, "running")
        finally:
            audit.close()

        # Only the recorded paths are needed (the run consumes the copies
        # inside the workspace), so the originals are not re-validated.
        inputs = RunInputs(
            source=Path(run["source_path"]),
            workbook=Path(run["workbook_path"]),
            task=run["task"],
            rules_file=None if run["rules_path"] is None else Path(run["rules_path"]),
            scoping_answers=None
            if run["scoping_answers_path"] is None
            else Path(run["scoping_answers_path"]),
            review_policy=None
            if run["review_policy_path"] is None
            else Path(run["review_policy_path"]),
        )
        progress.emit(f"Resuming run {run_id}...")
        execution = WorkflowExecution(
            workspace=workspace,
            inputs=inputs,
            runtimes=runtimes,
            runs_root=Path(runs_root),
            run_id=run_id,
            progress=progress,
            cancellation=cancellation,
        )
        return _invoke(execution, None)
    except WorkflowCancelled:
        progress.cancelled()
        raise
    except BaseException as exc:
        progress.failed(exc)
        raise


def _invoke(execution, initial_state):
    workspace = execution.workspace
    run_id = execution.run_id
    audit = AuditStore(workspace.audit_db)
    checkpoint_conn = sqlite3.connect(workspace.checkpoint_db, check_same_thread=False)
    try:
        graph = build_graph(execution, audit, SqliteSaver(checkpoint_conn))
        config = {"configurable": {"thread_id": run_id}}
        if initial_state is not None:
            graph_input = initial_state
        elif graph.get_state(config).interrupts:
            # A pending pause consumes a resume value; a crashed run
            # continues from its checkpoint with no input.
            graph_input = Command(resume=True)
        else:
            graph_input = None

        try:
            final_state = graph.invoke(graph_input, config)
        except WorkflowCancelled:
            audit.record_run_finished(run_id, "cancelled")
            raise
        except BaseException:
            # Kill or failure: the checkpoint survives for a later
            # resume; the run row records the abnormal exit.
            audit.record_run_finished(run_id, "failed")
            raise

        if "__interrupt__" in final_state:
            audit.record_run_status(run_id, "paused")
            answers_path = final_state["__interrupt__"][0].value["answers_path"]
            execution.progress.emit("Run paused: scoping questions need your answers.")
            execution.progress.emit(f"Edit the answers file: {answers_path}")
            execution.progress.emit(
                f"Then run: workflow resume --run-id {run_id}"
                f" --runs-root {execution.runs_root}"
            )
            execution.progress.paused(
                "Scoping questions need answers",
                workspace.scoping_questions_json,
            )
        else:
            execution.progress.emit(f"Run complete. Output: {workspace.final_xlsx}")
            execution.progress.completed(workspace.final_xlsx)
        return final_state
    finally:
        checkpoint_conn.close()
        audit.close()
