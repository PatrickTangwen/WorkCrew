import json

import pytest
from openpyxl import Workbook

WORKBOOK_SCHEMA_CONFIG = {
    "sheets": [
        {
            "name": "7) Practicum Courses",
            "target": True,
            "notes_field": "Notes",
            "title_field": "Project ID*",
            "overview_fields": ["Maturity", "Main Issue Area(s)"],
            "fields": {
                "Project ID*": {
                    "required": True,
                    "type": "id",
                    "column": "A",
                    "pattern": r"^PRJ-\d{4}$",
                    "value_kind": "constructed",
                    "writable": True,
                },
                "Start Date": {"type": "date", "column": "D", "writable": True},
                "Maturity": {
                    "type": "string",
                    "column": "E",
                    "value_kind": "mapped",
                    "writable": True,
                },
                "Notes": {"type": "string", "column": "F", "writable": True},
                "Main Issue Area(s)": {
                    "type": "controlled_vocabulary",
                    "column": "G",
                    "values": ["Healthcare", "Education"],
                    "writable": True,
                },
            },
        }
    ]
}


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source_documents"
    (source / "India 2008").mkdir(parents=True)
    (source / "India 2008" / "Project_Brief.txt").write_text(
        "Community healthcare delivery project."
    )
    (source / "archive_notes.md").write_text("Top-level archive notes.")
    # Unreadable-for-agents file; must surface in manifest and handoff.
    (source / "legacy_archive.zip").write_bytes(b"PK\x03\x04 opaque")

    workbook = tmp_path / "template.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "7) Practicum Courses"
    sheet["A1"] = "Project ID*"
    sheet["F1"] = "Notes"
    sheet["H1"] = "Total"
    sheet["H2"] = "=SUM(1,2)"
    book.save(workbook)

    rules = tmp_path / "rules"
    rules.mkdir()
    (rules / "naming.md").write_text("Naming conventions.")

    workbook_schema = tmp_path / "workbook_schema.json"
    workbook_schema.write_text(json.dumps(WORKBOOK_SCHEMA_CONFIG))

    # Pre-provided scoping answers keep straight-through runs (most
    # tests) from pausing; scoping-pause tests simply omit this input.
    scoping_answers = tmp_path / "scoping_answers.md"
    scoping_answers.write_text("Q1: One row per source folder.\n")

    return {
        "source": source,
        "workbook": workbook,
        "rules": rules,
        "workbook_schema": workbook_schema,
        "scoping_answers": scoping_answers,
        "runs_root": tmp_path / "runs",
    }
