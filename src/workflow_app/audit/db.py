"""SQLite audit store (plan section 36): runs and stages for ticket #2.

Mutation and finding tables arrive with the workbook safety layer (#4)
and review routing (#6).
"""

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
    rules_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT
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

    def record_run_started(self, run_id, source, workbook, rules):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO runs (run_id, status, started_at,"
                " source_path, workbook_path, rules_path)"
                " VALUES (?, 'running', ?, ?, ?, ?)",
                (run_id, _now(), str(source), str(workbook), str(rules)),
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

    def get_run(self, run_id):
        row = (
            self._connect()
            .execute(
                "SELECT run_id, status, started_at, finished_at,"
                " source_path, workbook_path, rules_path"
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
