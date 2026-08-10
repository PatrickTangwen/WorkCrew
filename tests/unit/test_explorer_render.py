"""Unit tests for explorer data assembly (plan section 22).

build_explorer_data is a pure derivation from draft workbook, schema,
provenance, handoff, and manifest — fixtures construct each input
directly and assertions inspect the returned data model.
"""

from openpyxl import Workbook

from workflow_app.ingestion.manifest import Manifest
from workflow_app.provenance.render import build_explorer_data
from workflow_app.workbook.schema import WorkbookSchema

SHEET = "7) Practicum Courses"

SCHEMA_CONFIG = {
    "sheets": [
        {
            "name": SHEET,
            "target": True,
            "title_field": "Organization",
            "overview_fields": ["Organization", "Main Issue Area(s)"],
            "fields": {
                "Project ID*": {"type": "id", "column": "A", "writable": True},
                "Organization": {
                    "type": "string",
                    "column": "B",
                    "writable": True,
                    "gloss_zh": "组织名称",
                },
                "Start Date": {"type": "date", "column": "D", "writable": True},
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


def make_schema(config=SCHEMA_CONFIG):
    return WorkbookSchema.model_validate(config)


def make_draft(tmp_path, cells):
    book = Workbook()
    sheet = book.active
    sheet.title = SHEET
    sheet["A1"] = "Project ID*"
    for ref, value in cells.items():
        sheet[ref] = value
    path = tmp_path / "draft.xlsx"
    book.save(path)
    return path


def make_manifest(paths=()):
    return Manifest.model_validate(
        {
            "files": [
                {
                    "path": path,
                    "type": "txt",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                    "status": "ok",
                }
                for path in paths
            ]
        }
    )


def empty_handoff():
    return {
        "sources": {"total": 0, "readable": 0, "unreadable": []},
        "records_evaluated": 0,
        "populated_cells": 0,
        "confidence_distribution": {"low": 0, "medium": 0, "high": 0},
        "evidence_summary": {},
        "decision_records": [],
        "missing_fields": [],
        "ambiguities": [],
        "source_conflicts": [],
        "extra_review": [],
    }


def provenance_entry(cell, value, source_file, reason="Stated in brief."):
    return {
        "cell": f"{SHEET}!{cell}",
        "value": value,
        "agent_role": "filler",
        "agent_runtime": "fake",
        "evidence": [
            {
                "source_file": source_file,
                "source_location": None,
                "evidence_type": "explicit_statement",
                "evidence_text": reason,
            }
        ],
        "rules_applied": [],
        "confidence": "high",
        "run_id": "run-1",
    }


def build(
    tmp_path,
    cells,
    provenance=(),
    manifest_paths=(),
    handoff=None,
    config=SCHEMA_CONFIG,
):
    return build_explorer_data(
        make_draft(tmp_path, cells),
        make_schema(config),
        {"entries": list(provenance)},
        handoff or empty_handoff(),
        make_manifest(manifest_paths),
    )


def test_rows_are_discovered_from_the_draft_in_row_order(tmp_path):
    data = build(
        tmp_path,
        {"A3": "PRJ-0002", "G3": "Education", "B2": "Health Org", "A2": "PRJ-0001"},
    )

    assert [row["row"] for row in data["rows"]] == [2, 3]
    first, second = data["rows"]
    assert first["title"] == "Health Org"
    # Row 3 has no value in the title field.
    assert second["title"] is None

    assert [field["name"] for field in first["fields"]] == [
        "Project ID*",
        "Organization",
        "Start Date",
        "Main Issue Area(s)",
    ]
    assert [field["column"] for field in first["fields"]] == ["A", "B", "D", "G"]
    by_name = {field["name"]: field for field in second["fields"]}
    assert by_name["Project ID*"]["value"] == "PRJ-0002"
    assert by_name["Organization"]["value"] is None


def test_fill_counts_use_schema_fields_only(tmp_path):
    data = build(
        tmp_path,
        # H is not a schema column; it must not count as filled.
        {"A2": "PRJ-0001", "G2": "Healthcare", "H2": "stray"},
    )

    assert data["field_count"] == 4
    (row,) = data["rows"]
    assert row["filled"] == 2


def test_rows_referenced_only_by_provenance_are_included(tmp_path):
    # A cleared cell can leave a draft row empty while provenance still
    # references it; the row must stay visible.
    data = build(
        tmp_path,
        {"A2": "PRJ-0001"},
        provenance=[provenance_entry("B5", None, "India 2008/brief.txt")],
    )

    assert [row["row"] for row in data["rows"]] == [2, 5]


def test_blank_proposal_row_and_decision_are_visible(tmp_path):
    handoff = empty_handoff()
    handoff["decision_records"] = [
        {
            "cell": f"{SHEET}!D5",
            "row": 5,
            "column_name": "Start Date",
            "status": "conflict",
            "value": None,
            "confidence": None,
            "evidence": [
                {
                    "source_file": "India 2008/brief.txt",
                    "source_location": "page 2",
                    "evidence_text": "The brief and addendum give different dates.",
                    "evidence_type": "direct",
                }
            ],
            "rules_applied": ["DATE_AUTHORITY"],
            "review_note": "The dates require human adjudication.",
        }
    ]

    data = build(
        tmp_path,
        {},
        handoff=handoff,
        manifest_paths=MANIFEST_PATHS,
    )

    assert [row["row"] for row in data["rows"]] == [5]
    (row,) = data["rows"]
    assert row["folders"] == ["India 2008"]
    field = next(item for item in row["fields"] if item["name"] == "Start Date")
    assert field["proposal"] == {
        "status": "conflict",
        "value": None,
        "confidence": None,
        "evidence": [
            {
                "file": "India 2008/brief.txt",
                "location": "page 2",
                "text": "The brief and addendum give different dates.",
                "type": "direct",
            }
        ],
        "rules_applied": ["DATE_AUTHORITY"],
        "review_note": "The dates require human adjudication.",
    }


def test_unrenderable_rejected_proposal_does_not_break_the_explorer(tmp_path):
    handoff = empty_handoff()
    handoff["decision_records"] = [
        {
            "cell": f"{SHEET}!12D",
            "row": 0,
            "column_name": "Start Date",
            "status": "proposed",
            "value": "2026-01-01",
            "confidence": "high",
            "evidence": [],
            "rules_applied": [],
            "review_note": "Rejected malformed address.",
        }
    ]
    handoff["extra_review"] = [
        {
            "cell": f"{SHEET}!12D",
            "reason": "malformed cell address '12D'",
        }
    ]

    data = build(tmp_path, {}, handoff=handoff)

    assert data["rows"] == []
    assert data["findings"][-1]["detail"] == "malformed cell address '12D'"


MANIFEST_PATHS = (
    "India 2008/brief.txt",
    "India 2008/report.pdf",
    "India 2009/notes.txt",
    "archive_notes.md",
)


def test_fields_carry_provenance_sources_and_author_role(tmp_path):
    entry = provenance_entry("A2", "PRJ-0001", "India 2008/brief.txt")
    entry["evidence"].append(
        {
            "source_file": "India 2008/report.pdf",
            "source_location": "p. 3",
            "evidence_type": "derived",
            "evidence_text": "Derived from the report header.",
        }
    )
    data = build(tmp_path, {"A2": "PRJ-0001", "B2": "Org"}, provenance=[entry])

    (row,) = data["rows"]
    by_name = {field["name"]: field for field in row["fields"]}
    assert by_name["Project ID*"]["role"] == "filler"
    assert by_name["Project ID*"]["sources"] == [
        {
            "file": "India 2008/brief.txt",
            "location": None,
            "text": "Stated in brief.",
            "type": "explicit_statement",
        },
        {
            "file": "India 2008/report.pdf",
            "location": "p. 3",
            "text": "Derived from the report header.",
            "type": "derived",
        },
    ]
    # No provenance for the Organization cell: manually pre-existing.
    assert by_name["Organization"]["sources"] == []
    assert by_name["Organization"]["role"] is None


def test_display_annotations_flow_into_the_data_model(tmp_path):
    data = build(tmp_path, {"A2": "PRJ-0001", "G2": "Healthcare, Education"})

    assert data["title"] == SHEET
    assert data["title_field"] == "Organization"
    assert data["overview_fields"] == ["Organization", "Main Issue Area(s)"]

    (row,) = data["rows"]
    by_name = {field["name"]: field for field in row["fields"]}
    # controlled_vocabulary values segment into pills only along
    # declared members; the behavior is type-driven, never a hardcoded
    # field name.
    assert by_name["Main Issue Area(s)"]["pill_values"] == ["Healthcare", "Education"]
    assert by_name["Project ID*"]["pill_values"] is None
    assert by_name["Organization"]["gloss_zh"] == "组织名称"
    assert by_name["Project ID*"]["gloss_zh"] is None
    assert data["populated_cells"] == sum(r["filled"] for r in data["rows"])


def test_vocabulary_values_containing_the_delimiter_stay_whole(tmp_path):
    config = {
        "sheets": [
            {
                "name": SHEET,
                "target": True,
                "fields": {
                    "Main Issue Area(s)": {
                        "type": "controlled_vocabulary",
                        "column": "G",
                        "values": ["Water, Sanitation & Hygiene", "Education"],
                        "writable": True,
                    },
                },
            }
        ]
    }
    data = build(tmp_path, {"G2": "Water, Sanitation & Hygiene"}, config=config)

    (row,) = data["rows"]
    (field,) = row["fields"]
    # "Water, Sanitation & Hygiene" contains ", " but is one declared
    # member — it must not split into bogus pills.
    assert field["pill_values"] == ["Water, Sanitation & Hygiene"]


def test_findings_collect_handoff_attention_items(tmp_path):
    handoff = empty_handoff()
    handoff["sources"]["unreadable"] = [{"path": "legacy.zip", "status": "UNSUPPORTED"}]
    handoff["ambiguities"] = [
        {"cell": f"{SHEET}!D2", "column_name": "Start Date", "notes": "Two dates."}
    ]
    handoff["source_conflicts"] = [
        {"cell": f"{SHEET}!G2", "column_name": "Main Issue Area(s)", "notes": None}
    ]
    handoff["extra_review"] = [
        {"cell": f"{SHEET}!A2", "reason": "written at low confidence"}
    ]

    data = build(tmp_path, {"A2": "PRJ-0001"}, handoff=handoff)

    assert data["findings"] == [
        {"kind": "unreadable_source", "ref": "legacy.zip", "detail": "UNSUPPORTED"},
        {
            "kind": "ambiguity",
            "ref": f"{SHEET}!D2 (Start Date)",
            "detail": "Two dates.",
        },
        {
            "kind": "source_conflict",
            "ref": f"{SHEET}!G2 (Main Issue Area(s))",
            "detail": None,
        },
        {
            "kind": "extra_review",
            "ref": f"{SHEET}!A2",
            "detail": "written at low confidence",
        },
    ]


def test_folders_follow_manifest_order_with_rows_from_evidence(tmp_path):
    data = build(
        tmp_path,
        {"A2": "PRJ-0001", "A3": "PRJ-0002"},
        provenance=[
            provenance_entry("A2", "PRJ-0001", "India 2008/brief.txt"),
            provenance_entry("A3", "PRJ-0002", "India 2009/notes.txt"),
            provenance_entry("B3", "Org", "India 2008/report.pdf"),
        ],
        manifest_paths=MANIFEST_PATHS,
    )

    assert [folder["name"] for folder in data["folders"]] == [
        "India 2008",
        "India 2009",
    ]
    by_name = {folder["name"]: folder for folder in data["folders"]}
    assert by_name["India 2008"]["rows"] == [2, 3]
    assert by_name["India 2009"]["rows"] == [3]

    first, second = data["rows"]
    # Primary folder = first evidence folder in manifest order.
    assert first["folders"] == ["India 2008"]
    assert second["folders"] == ["India 2008", "India 2009"]


def test_undeclared_duplicate_folders_are_not_inferred_as_merged(tmp_path):
    # Every India 2009 file fed row 2 — the shape the old inference
    # flagged. Without an explicit Filler declaration the explorer
    # claims nothing (ADR 0015: the declaration replaced the inference
    # and its cross-citation false positives).
    data = build(
        tmp_path,
        {"A2": "PRJ-0001"},
        provenance=[
            provenance_entry("A2", "PRJ-0001", "India 2008/brief.txt"),
            provenance_entry("B2", "Org", "India 2009/notes.txt"),
        ],
        manifest_paths=MANIFEST_PATHS,
    )

    by_name = {folder["name"]: folder for folder in data["folders"]}
    assert by_name["India 2009"]["merged_into"] is None
    (row,) = data["rows"]
    assert row["merged_from"] == []


def test_declared_merges_mark_folder_and_row(tmp_path):
    # The declaration alone drives the marking — India 2009 needs no
    # cited evidence at all (a fully ignored duplicate folder).
    handoff = empty_handoff()
    handoff["merges"] = [
        {
            "folders": ["India 2009"],
            "row": 2,
            "reason": "Same project; the 2009 folder is a re-upload.",
        }
    ]
    data = build(
        tmp_path,
        {"A2": "PRJ-0001"},
        provenance=[provenance_entry("A2", "PRJ-0001", "India 2008/brief.txt")],
        manifest_paths=MANIFEST_PATHS,
        handoff=handoff,
    )

    by_name = {folder["name"]: folder for folder in data["folders"]}
    merged = by_name["India 2009"]
    assert merged["merged_into"] == 2
    assert "re-upload" in merged["merge_reason"]
    assert by_name["India 2008"]["merged_into"] is None
    assert by_name["India 2008"]["merge_reason"] is None
    (row,) = data["rows"]
    assert row["merged_from"] == ["India 2009"]


def test_declared_merges_join_the_findings_list(tmp_path):
    handoff = empty_handoff()
    handoff["merges"] = [
        {
            "folders": ["India 2009"],
            "row": 2,
            "reason": "Same project; the 2009 folder is a re-upload.",
        }
    ]
    data = build(
        tmp_path,
        {"A2": "PRJ-0001"},
        manifest_paths=MANIFEST_PATHS,
        handoff=handoff,
    )

    (merge_finding,) = [f for f in data["findings"] if f["kind"] == "merge"]
    assert merge_finding["ref"] == "India 2009 -> row 2"
    assert "re-upload" in merge_finding["detail"]


def test_unrenderable_declarations_get_no_navigation_markings(tmp_path):
    # A phantom folder or a nonexistent surviving row cannot be badged
    # or linked; the declaration stays visible in the handoff and the
    # findings list.
    handoff = empty_handoff()
    handoff["merges"] = [
        {"folders": ["Ghost 2010"], "row": 2, "reason": "Phantom folder."},
        {"folders": ["India 2009"], "row": 99, "reason": "Row never filled."},
    ]
    data = build(
        tmp_path,
        {"A2": "PRJ-0001"},
        manifest_paths=MANIFEST_PATHS,
        handoff=handoff,
    )

    assert all(folder["merged_into"] is None for folder in data["folders"])
    (row,) = data["rows"]
    assert row["merged_from"] == []
    assert len([f for f in data["findings"] if f["kind"] == "merge"]) == 2


def test_rows_and_folders_without_evidence_links_stay_visible(tmp_path):
    # Row 3 has no folder evidence (top-level file only); India 2009
    # has files but no referencing row. Both remain visible facts.
    data = build(
        tmp_path,
        {"A2": "PRJ-0001", "A3": "PRJ-0002"},
        provenance=[
            provenance_entry("A2", "PRJ-0001", "India 2008/brief.txt"),
            provenance_entry("A3", "PRJ-0002", "archive_notes.md"),
        ],
        manifest_paths=MANIFEST_PATHS,
    )

    by_name = {folder["name"]: folder for folder in data["folders"]}
    assert by_name["India 2009"]["rows"] == []
    assert by_name["India 2009"]["merged_into"] is None
    assert data["ungrouped_rows"] == [3]
    assert data["rows"][1]["folders"] == []
