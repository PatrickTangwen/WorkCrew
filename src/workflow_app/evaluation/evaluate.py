"""Run-workspace evaluation loader (ticket #13, plan section 42).

Extracts the facts a completed run leaves behind — final workbook
cells, the filler's audited draft values, provenance, review findings,
revision decisions, and the unresolved set — and hands them to the
pure metric core. Only completed runs are evaluable: the final
workbook is the object under test.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from workflow_app.evaluation.metrics import compute_metrics


def _final_cells(workspace, labels):
    sheet = load_workbook(workspace / "output/final.xlsx")[labels.sheet]
    return {
        label.cell: sheet[label.cell].value
        for row in labels.rows
        for label in row.fields.values()
    }


def _draft_cells(workspace):
    # The filler's applied audit mutations are the draft as reviewed;
    # idempotent replays add no rows, so last-write-per-cell is exact.
    with sqlite3.connect(workspace / "state/audit.sqlite") as conn:
        rows = conn.execute(
            "SELECT cell, new_value FROM mutations"
            " WHERE actor_role = 'filler' AND status = 'applied' ORDER BY id"
        ).fetchall()
    return {cell: json.loads(value) for cell, value in rows}


def _artifact(workspace, name, default):
    path = workspace / "artifacts" / name
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def _duration_seconds(started_at, finished_at):
    if started_at is None or finished_at is None:
        return None
    return (
        datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)
    ).total_seconds()


def _run_facts(workspace):
    # Runtime context for cross-configuration comparison (plan section
    # 42): overall duration plus per-stage rows from the audit store.
    with sqlite3.connect(workspace / "state/audit.sqlite") as conn:
        status, started_at, finished_at = conn.execute(
            "SELECT status, started_at, finished_at FROM runs"
        ).fetchone()
        stage_rows = conn.execute(
            "SELECT stage, status, started_at, finished_at FROM stages ORDER BY id"
        ).fetchall()
    return {
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": _duration_seconds(started_at, finished_at),
        "stages": [
            {
                "stage": stage,
                "status": stage_status,
                "duration_seconds": _duration_seconds(stage_started, stage_finished),
            }
            for stage, stage_status, stage_started, stage_finished in stage_rows
        ],
    }


def evaluate_run(workspace, labels):
    workspace = Path(workspace)
    if not (workspace / "output/final.xlsx").is_file():
        raise FileNotFoundError(
            f"run has no final workbook to evaluate: {workspace / 'output/final.xlsx'}"
        )

    provenance = _artifact(workspace, "provenance.json", {"entries": []})["entries"]
    findings = _artifact(workspace, "review.json", {"findings": []})["findings"]
    decisions = _artifact(workspace, "revision.json", {"decisions": []})["decisions"]
    unresolved = [
        item["cell"]
        for item in _artifact(workspace, "unresolved.json", {"cells": []})["cells"]
    ]

    evaluation = compute_metrics(
        labels,
        _final_cells(workspace, labels),
        _draft_cells(workspace),
        provenance,
        findings,
        decisions,
        unresolved,
    )
    evaluation["run_id"] = workspace.name
    evaluation["run"] = _run_facts(workspace)
    return evaluation
