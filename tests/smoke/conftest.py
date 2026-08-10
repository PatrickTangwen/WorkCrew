"""Sample workspace for live Claude Code smoke tests (ticket #10).

A small but information-rich workspace: one project folder whose brief
supports a date, a maturity judgment, an issue area, and a constructed
Project ID, so a live fill has concrete material to cite.
"""

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

PROJECT_BRIEF = """\
Project Brief — Community Health Outreach, India

The community healthcare delivery project began operations on 2008-03-15
in rural Maharashtra. The program trained village health workers and ran
mobile clinics; by the end of its first year it had an established
partner network and recurring funding, and the team considered the
program well established.

Primary focus: community healthcare delivery.
"""

RULES = """\
# Extraction rules

- Project ID is constructed as PRJ-<four-digit start year> (e.g. a
  project starting in 2008 gets PRJ-2008).
- Start Date uses ISO format YYYY-MM-DD.
- Maturity is a judgment on a scale: Nascent, Developing, Established.
- Main Issue Area(s) must use the controlled vocabulary from the
  workbook schema.
"""


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "source_documents"
    (source / "India 2008").mkdir(parents=True)
    (source / "India 2008" / "Project_Brief.txt").write_text(PROJECT_BRIEF)

    workbook = tmp_path / "template.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "7) Practicum Courses"
    for cell, header in (
        ("A1", "Project ID*"),
        ("D1", "Start Date"),
        ("E1", "Maturity"),
        ("F1", "Notes"),
        ("G1", "Main Issue Area(s)"),
    ):
        sheet[cell] = header
    book.save(workbook)

    rules_file = tmp_path / "rules.md"
    rules_file.write_text(RULES)

    scoping_answers = tmp_path / "scoping_answers.md"
    scoping_answers.write_text(
        "One row per source folder (one project per folder), starting at "
        "row 2. The 'India 2008' folder is the complete authoritative set "
        "for this run.\n"
    )

    return {
        "source": source,
        "workbook": workbook,
        "task": (
            "Fill one row per project folder: the constructed Project ID, "
            "start date, maturity judgment, and issue area."
        ),
        "rules_file": rules_file,
        "scoping_answers": scoping_answers,
        "runs_root": tmp_path / "runs",
    }


def scoping_fixture():
    """Schema the live scoping pass would derive, for tests exercising a
    later stage."""
    return {
        "workbook_schema": WORKBOOK_SCHEMA_CONFIG,
        "questions": [
            {"id": "Q1", "question": "One row per folder?", "type": "confirm"}
        ],
    }
