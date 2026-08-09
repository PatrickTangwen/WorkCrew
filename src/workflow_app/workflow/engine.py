"""Workflow engine entries: start a run, resume a paused one.

This is the primary test seam: callers inject agent runtimes (fake in
tests and during fake-first development, live adapters later). Graph
state persists through a SqliteSaver checkpoint database inside the
run's state/ directory (plan section 30), keyed by run id.
"""

import sqlite3
import time
import uuid
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from workflow_app.audit.db import AuditStore
from workflow_app.progress import emit
from workflow_app.workbook.schema import load_workbook_schema
from workflow_app.workflow.graph import build_graph
from workflow_app.workspace import RunInputs, Workspace


def new_run_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def run_workflow(inputs, runs_root, runtimes):
    inputs.validate()
    # Fail fast on a malformed schema config — before the workspace
    # exists and long before any agent could be invoked (ticket #3).
    load_workbook_schema(inputs.workbook_schema)

    run_id = new_run_id()
    # Resolved so the paths persisted into checkpointed state stay valid
    # when the run is resumed from a different working directory.
    workspace = Workspace((Path(runs_root) / run_id).resolve())
    workspace.create_layout()
    emit(f"Starting run {run_id}...")

    initial_state = {
        "run_id": run_id,
        "workspace_path": str(workspace.root),
        "manifest_path": None,
        "schema_path": None,
        "scoping_questions_path": None,
        "scoping_answers_path": None,
        "extraction_path": None,
        "draft_xlsx_path": None,
        "review_path": None,
        "revision_path": None,
        "re_review_path": None,
        "phase": "",
    }
    return _invoke(workspace, inputs, runtimes, runs_root, run_id, initial_state)


def resume_workflow(run_id, runs_root, runtimes):
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
        rules=Path(run["rules_path"]),
        workbook_schema=Path(run["workbook_schema_path"]),
        scoping_answers=None
        if run["scoping_answers_path"] is None
        else Path(run["scoping_answers_path"]),
    )

    emit(f"Resuming run {run_id}...")
    return _invoke(workspace, inputs, runtimes, runs_root, run_id, None)


def _invoke(workspace, inputs, runtimes, runs_root, run_id, initial_state):
    audit = AuditStore(workspace.audit_db)
    checkpoint_conn = sqlite3.connect(workspace.checkpoint_db, check_same_thread=False)
    try:
        graph = build_graph(
            workspace, inputs, runtimes, audit, SqliteSaver(checkpoint_conn)
        )
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
        except BaseException:
            # Kill or failure: the checkpoint survives for a later
            # resume; the run row records the abnormal exit.
            audit.record_run_finished(run_id, "failed")
            raise

        if "__interrupt__" in final_state:
            audit.record_run_status(run_id, "paused")
            answers_path = final_state["__interrupt__"][0].value["answers_path"]
            emit("Run paused: scoping questions need your answers.")
            emit(f"Edit the answers file: {answers_path}")
            emit(f"Then run: workflow resume --run-id {run_id} --runs-root {runs_root}")
        else:
            emit(f"Run complete. Output: {workspace.final_xlsx}")
        return final_state
    finally:
        checkpoint_conn.close()
        audit.close()
