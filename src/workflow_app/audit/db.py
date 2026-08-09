"""SQLite audit store (plan section 36): runs, stages, and mutations.

Finding tables arrive with review routing (#6). Cell values in mutation
rows are JSON-encoded so their types survive the round trip.
"""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_path TEXT NOT NULL,
    workbook_path TEXT NOT NULL,
    rules_path TEXT NOT NULL,
    workbook_schema_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS mutations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sheet TEXT NOT NULL,
    cell TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    actor_role TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);
"""


def _now():
    return datetime.now(UTC).isoformat()


class AuditStore:
    def __init__(self, db_path):
        self._db_path = Path(db_path)
        self._conn = None

    def _connect(self):
        # The workspace layout (including the parent state/ directory) is
        # created by the engine before the graph runs.
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def record_run_started(self, run_id, inputs):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO runs (run_id, status, started_at, source_path,"
                " workbook_path, rules_path, workbook_schema_path)"
                " VALUES (?, 'running', ?, ?, ?, ?, ?)",
                (
                    run_id,
                    _now(),
                    str(inputs.source),
                    str(inputs.workbook),
                    str(inputs.rules),
                    str(inputs.workbook_schema),
                ),
            )

    def record_run_finished(self, run_id, status):
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, _now(), run_id),
            )

    def record_stage_started(self, run_id, stage):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO stages (run_id, stage, status, started_at)"
                " VALUES (?, ?, 'started', ?)",
                (run_id, stage, _now()),
            )

    def record_stage_finished(self, run_id, stage):
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE stages SET status = 'completed', finished_at = ?"
                " WHERE run_id = ? AND stage = ? AND finished_at IS NULL",
                (_now(), run_id, stage),
            )

    def record_mutation(self, run_id, record):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO mutations (run_id, sheet, cell, old_value, new_value,"
                " actor_role, source_ref, status, reason, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    record["sheet"],
                    record["cell"],
                    json.dumps(record["old_value"]),
                    json.dumps(record["new_value"]),
                    record["actor_role"],
                    record["source_ref"],
                    record["status"],
                    record["reason"],
                    _now(),
                ),
            )

    def find_applied_mutation(self, run_id, sheet, cell, actor_role, source_ref):
        row = (
            self._connect()
            .execute(
                "SELECT new_value FROM mutations"
                " WHERE run_id = ? AND sheet = ? AND cell = ?"
                " AND actor_role = ? AND source_ref = ? AND status = 'applied'"
                " ORDER BY id DESC LIMIT 1",
                (run_id, sheet, cell, actor_role, source_ref),
            )
            .fetchone()
        )
        if row is None:
            return None
        return {"new_value": json.loads(row[0])}

    def get_run(self, run_id):
        row = (
            self._connect()
            .execute(
                "SELECT run_id, status, started_at, finished_at, source_path,"
                " workbook_path, rules_path, workbook_schema_path"
                " FROM runs WHERE run_id = ?",
                (run_id,),
            )
            .fetchone()
        )
        if row is None:
            raise KeyError(f"run {run_id!r} not found in audit store")
        keys = (
            "run_id",
            "status",
            "started_at",
            "finished_at",
            "source_path",
            "workbook_path",
            "rules_path",
            "workbook_schema_path",
        )
        return dict(zip(keys, row, strict=True))

    def list_stages(self, run_id):
        rows = (
            self._connect()
            .execute(
                "SELECT stage, status, started_at, finished_at"
                " FROM stages WHERE run_id = ? ORDER BY id",
                (run_id,),
            )
            .fetchall()
        )
        keys = ("stage", "status", "started_at", "finished_at")
        return [dict(zip(keys, row, strict=True)) for row in rows]
