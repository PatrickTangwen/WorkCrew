"""SQLite audit store (plan section 36): runs, stages, mutations, events.

Finding tables arrive with review routing (#6). Cell values in mutation
rows and event payloads are JSON-encoded so their types survive the
round trip.
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
    task TEXT NOT NULL,
    rules_path TEXT,
    scoping_answers_path TEXT,
    review_policy_path TEXT
);

CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    failure TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    kind TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL
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
            self._migrate()
        return self._conn

    def _migrate(self):
        # CREATE TABLE IF NOT EXISTS never alters an existing table, so
        # audit databases from runs started before a column landed must
        # be upgraded here or those runs become unresumable (#9).
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(runs)")}
        if "review_policy_path" not in columns:
            with self._conn:
                self._conn.execute(
                    "ALTER TABLE runs ADD COLUMN review_policy_path TEXT"
                )
        if "task" not in columns:
            # Runs recorded before the task became an input (ADR 0032)
            # keep a NULL task. They stay listable and readable; they are
            # not resumable, because their schema came from a file the
            # new graph no longer consults.
            with self._conn:
                self._conn.execute("ALTER TABLE runs ADD COLUMN task TEXT")

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def record_run_started(self, run_id, inputs):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO runs (run_id, status, started_at, source_path,"
                " workbook_path, task, rules_path,"
                " scoping_answers_path, review_policy_path)"
                " VALUES (?, 'running', ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    _now(),
                    str(inputs.source),
                    str(inputs.workbook),
                    inputs.task,
                    None if inputs.rules_file is None else str(inputs.rules_file),
                    None
                    if inputs.scoping_answers is None
                    else str(inputs.scoping_answers),
                    None if inputs.review_policy is None else str(inputs.review_policy),
                ),
            )

    def record_run_finished(self, run_id, status):
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                (status, _now(), run_id),
            )

    def record_run_status(self, run_id, status):
        # Non-terminal transitions (paused, running) clear any
        # finished_at stamped by an earlier abnormal exit.
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE runs SET status = ?, finished_at = NULL WHERE run_id = ?",
                (status, run_id),
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
        # Only the most recent unfinished entry completes: earlier
        # dangling 'started' rows record entries that were interrupted
        # (paused or crashed) and stay that way as audit facts.
        conn = self._connect()
        with conn:
            conn.execute(
                "UPDATE stages SET status = 'completed', finished_at = ?"
                " WHERE id = (SELECT MAX(id) FROM stages"
                "  WHERE run_id = ? AND stage = ? AND finished_at IS NULL)",
                (_now(), run_id, stage),
            )

    def _update_latest_unfinished_stage(self, run_id, stage, assignments, params):
        conn = self._connect()
        with conn:
            conn.execute(
                f"UPDATE stages SET {assignments}"
                " WHERE id = (SELECT MAX(id) FROM stages"
                "  WHERE run_id = ? AND stage = ? AND finished_at IS NULL)",
                (*params, run_id, stage),
            )

    def record_stage_retry(self, run_id, stage):
        self._update_latest_unfinished_stage(
            run_id, stage, "retry_count = retry_count + 1", ()
        )

    def record_stage_failed(self, run_id, stage, classification):
        self._update_latest_unfinished_stage(
            run_id,
            stage,
            "status = 'failed', failure = ?, finished_at = ?",
            (classification, _now()),
        )

    def record_stage_cancelled(self, run_id, stage):
        self._update_latest_unfinished_stage(
            run_id,
            stage,
            "status = 'cancelled', failure = 'cancelled', finished_at = ?",
            (_now(),),
        )

    def record_stage_degraded(self, run_id, stage, classification):
        # The stage completes (the run continues), but its output was
        # degraded after exhausted retries; the classification records
        # why. record_stage_finished still stamps completion.
        self._update_latest_unfinished_stage(
            run_id, stage, "failure = ?", (classification,)
        )

    def record_event(self, run_id, kind, payload):
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO events (run_id, kind, payload, created_at)"
                " VALUES (?, ?, ?, ?)",
                (run_id, kind, json.dumps(payload), _now()),
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

    def list_applied_mutations(self, run_id, actor_role):
        rows = (
            self._connect()
            .execute(
                "SELECT sheet, cell, old_value, new_value, source_ref"
                " FROM mutations WHERE run_id = ? AND actor_role = ?"
                " AND status = 'applied' ORDER BY id",
                (run_id, actor_role),
            )
            .fetchall()
        )
        return [
            {
                "sheet": sheet,
                "cell": cell,
                "old_value": json.loads(old_value),
                "new_value": json.loads(new_value),
                "source_ref": source_ref,
            }
            for sheet, cell, old_value, new_value, source_ref in rows
        ]

    def get_run(self, run_id):
        row = (
            self._connect()
            .execute(
                "SELECT run_id, status, started_at, finished_at, source_path,"
                " workbook_path, task, rules_path,"
                " scoping_answers_path, review_policy_path"
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
            "task",
            "rules_path",
            "scoping_answers_path",
            "review_policy_path",
        )
        return dict(zip(keys, row, strict=True))

    def list_stages(self, run_id):
        rows = (
            self._connect()
            .execute(
                "SELECT stage, status, started_at, finished_at, retry_count,"
                " failure FROM stages WHERE run_id = ? ORDER BY id",
                (run_id,),
            )
            .fetchall()
        )
        keys = (
            "stage",
            "status",
            "started_at",
            "finished_at",
            "retry_count",
            "failure",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]
