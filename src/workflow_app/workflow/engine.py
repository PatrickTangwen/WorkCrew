"""Workflow engine entry.

This is the primary test seam: callers inject agent runtimes (fake in
tests and during fake-first development, live adapters later).
"""

import time
import uuid
from pathlib import Path

from workflow_app.audit.db import AuditStore
from workflow_app.progress import emit
from workflow_app.workbook.schema import load_workbook_schema
from workflow_app.workflow.graph import build_graph
from workflow_app.workspace import Workspace


def new_run_id():
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def run_workflow(inputs, runs_root, runtimes):
    inputs.validate()
    # Fail fast on a malformed schema config — before the workspace
    # exists and long before any agent could be invoked (ticket #3).
    load_workbook_schema(inputs.workbook_schema)

    run_id = new_run_id()
    workspace = Workspace(Path(runs_root) / run_id)
    workspace.create_layout()
    audit = AuditStore(workspace.audit_db)
    emit(f"Starting run {run_id}...")

    graph = build_graph(workspace, inputs, runtimes, audit)
    initial_state = {
        "run_id": run_id,
        "workspace_path": str(workspace.root),
        "manifest_path": None,
        "schema_path": None,
        "extraction_path": None,
        "draft_xlsx_path": None,
        "phase": "",
    }
    try:
        final_state = graph.invoke(initial_state)
    finally:
        audit.close()

    emit(f"Run complete. Workspace: {workspace.root}")
    return final_state
