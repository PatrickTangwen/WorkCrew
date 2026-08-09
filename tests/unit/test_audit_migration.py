"""Audit databases from runs started before newer columns landed must
stay readable, or crash resume (#9) breaks for those runs."""

import sqlite3

from workflow_app.audit.db import AuditStore

PRE_TICKET_11_RUNS_DDL = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_path TEXT NOT NULL,
    workbook_path TEXT NOT NULL,
    rules_path TEXT NOT NULL,
    workbook_schema_path TEXT NOT NULL,
    scoping_answers_path TEXT
);
"""


def test_pre_review_policy_audit_db_is_upgraded_on_open(tmp_path):
    db_path = tmp_path / "audit.sqlite"
    conn = sqlite3.connect(db_path)
    with conn:
        conn.executescript(PRE_TICKET_11_RUNS_DDL)
        conn.execute(
            "INSERT INTO runs (run_id, status, started_at, source_path,"
            " workbook_path, rules_path, workbook_schema_path,"
            " scoping_answers_path)"
            " VALUES ('r1', 'failed', 't0', 's', 'w', 'r', 'c', NULL)"
        )
    conn.close()

    store = AuditStore(db_path)
    try:
        run = store.get_run("r1")
    finally:
        store.close()
    assert run["status"] == "failed"
    assert run["review_policy_path"] is None
