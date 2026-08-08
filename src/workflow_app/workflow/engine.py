"""Workflow engine entry.

This is the primary test seam: callers inject agent runtimes (fake in
tests and during fake-first development, live adapters later).
"""

import time
import uuid
from pathlib import Path

from workflow_app.audit.db import AuditStore
from workflow_app.progress import emit
from workflow_app.workflow.graph import build_graph
from workflow_app.workspace import Workspace


def new_run_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def run_workflow(source, workbook, rules, runs_root, runtimes):
    source, workbook, rules = Path(source), Path(workbook), Path(rules)
    if not source.is_dir():
        raise FileNotFoundError(f"source folder not found: {source}")
    if not workbook.is_file():
        raise FileNotFoundError(f"workbook not found: {workbook}")
    if not rules.is_dir():
        raise FileNotFoundError(f"rules folder not found: {rules}")

    run_id = new_run_id()
    workspace = Workspace(Path(runs_root) / run_id)
    audit = AuditStore(workspace.audit_db)
    emit(f"Starting run {run_id}...")

    graph = build_graph(workspace, source, workbook, rules, runtimes, audit)
    initial_state = {
        "run_id": run_id,
        "workspace_path": str(workspace.root),
        "extraction_path": None,
        "phase": "",
    }
    try:
        final_state = graph.invoke(initial_state)
    finally:
        audit.close()

    emit(f"Run complete. Workspace: {workspace.root}")
    return final_state
