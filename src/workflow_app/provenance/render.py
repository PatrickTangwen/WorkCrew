"""Explorer data assembly (plan section 22).

Builds the language-neutral data model the review explorer embeds,
deterministically, from the draft workbook, provenance, handoff, and
manifest. Rendering to HTML lives in provenance/explorer.py. Workbook
access goes through the writer isolation layer (plan section 14).
"""

from workflow_app.workbook import writer

# Row 1 holds the column headers; data rows start below it (the layout
# the section-16 schema config describes columns for).
FIRST_DATA_ROW = 2


def _json_value(value):
    # Cell values must survive JSON embedding; dates and other rich
    # types render as their string form.
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _pill_values(value, spec):
    # Display segmentation for controlled vocabularies: split only when
    # every part is a declared member (multi-select cells serialize as
    # ", "-joined members); otherwise the value renders whole.
    if spec.type != "controlled_vocabulary" or not isinstance(value, str):
        return None
    parts = value.split(", ")
    if all(part in spec.values for part in parts):
        return parts
    return [value]


def _row_numbers(book, sheet, provenance):
    rows = set()
    columns = [spec.column for spec in sheet.fields.values() if spec.column]
    for row in range(FIRST_DATA_ROW, writer.max_row(book, sheet.name) + 1):
        if any(
            writer.read_cell(book, sheet.name, f"{column}{row}") is not None
            for column in columns
        ):
            rows.add(row)
    for entry in provenance["entries"]:
        entry_sheet, cell_ref = entry["cell"].split("!", 1)
        if entry_sheet == sheet.name:
            rows.add(writer.row_of(cell_ref))
    return sorted(rows)


def _folder_names(manifest):
    # Top-level source directories in manifest traversal order.
    names = []
    for entry in manifest.files:
        head, separator, _ = entry.path.partition("/")
        if separator and head not in names:
            names.append(head)
    return names


def _row_folders(sheet, provenance, folder_names):
    # Row -> evidence folders, each row's list in manifest order.
    known = set(folder_names)
    referenced = {}
    for entry in provenance["entries"]:
        entry_sheet, cell_ref = entry["cell"].split("!", 1)
        if entry_sheet != sheet.name:
            continue
        row = writer.row_of(cell_ref)
        for evidence in entry["evidence"]:
            source = evidence["source_file"] or ""
            head, separator, _ = source.partition("/")
            if separator and head in known:
                referenced.setdefault(row, set()).add(head)
    return {
        row: [name for name in folder_names if name in heads]
        for row, heads in referenced.items()
    }


def _findings(handoff):
    findings = [
        {
            "kind": "unreadable_source",
            "ref": item["path"],
            "detail": item["status"],
        }
        for item in handoff["sources"]["unreadable"]
    ]
    for kind, key in (
        ("ambiguity", "ambiguities"),
        ("source_conflict", "source_conflicts"),
    ):
        findings += [
            {
                "kind": kind,
                "ref": f"{item['cell']} ({item['column_name']})",
                "detail": item["notes"],
            }
            for item in handoff[key]
        ]
    findings += [
        {"kind": "extra_review", "ref": item["cell"], "detail": item["reason"]}
        for item in handoff["extra_review"]
    ]
    return findings


def build_explorer_data(draft_path, schema, provenance, handoff, manifest):
    sheet = schema.target_sheet()
    book = writer.open_draft(draft_path)

    entries_by_cell = {}
    for entry in provenance["entries"]:
        entry_sheet, cell_ref = entry["cell"].split("!", 1)
        if entry_sheet == sheet.name:
            entries_by_cell[cell_ref] = entry

    folder_names = _folder_names(manifest)
    row_folders = _row_folders(sheet, provenance, folder_names)
    row_numbers = _row_numbers(book, sheet, provenance)
    folder_rows = {
        name: [row for row in row_numbers if name in row_folders.get(row, [])]
        for name in folder_names
    }
    # A duplicate source folder was merged when its entire evidence
    # went into a single row that primarily belongs to another folder.
    merged_into = {
        name: rows[0]
        for name, rows in folder_rows.items()
        if len(rows) == 1 and row_folders[rows[0]][0] != name
    }

    rows = []
    for row_number in row_numbers:
        fields = []
        for name, spec in sheet.fields.items():
            value = (
                _json_value(
                    writer.read_cell(book, sheet.name, f"{spec.column}{row_number}")
                )
                if spec.column
                else None
            )
            entry = (
                entries_by_cell.get(f"{spec.column}{row_number}")
                if spec.column
                else None
            )
            fields.append(
                {
                    "name": name,
                    "column": spec.column,
                    "value": value,
                    "role": entry["agent_role"] if entry else None,
                    "pill_values": _pill_values(value, spec),
                    "gloss_zh": spec.gloss_zh,
                    "sources": [
                        {
                            "file": evidence["source_file"],
                            "location": evidence["source_location"],
                            "text": evidence["evidence_text"],
                        }
                        for evidence in entry["evidence"]
                    ]
                    if entry
                    else [],
                }
            )
        title = None
        if sheet.title_field is not None:
            title = next(
                field["value"] for field in fields if field["name"] == sheet.title_field
            )
        rows.append(
            {
                "row": row_number,
                "title": title,
                "filled": sum(1 for field in fields if field["value"] is not None),
                "folders": row_folders.get(row_number, []),
                "merged_from": [
                    name for name, target in merged_into.items() if target == row_number
                ],
                "fields": fields,
            }
        )

    return {
        "title": sheet.name,
        "title_field": sheet.title_field,
        "overview_fields": sheet.overview_fields,
        "rows": rows,
        "folders": [
            {
                "name": name,
                "rows": folder_rows[name],
                "merged_into": merged_into.get(name),
            }
            for name in folder_names
        ],
        "ungrouped_rows": [row for row in row_numbers if not row_folders.get(row)],
        "findings": _findings(handoff),
        "field_count": len(sheet.fields),
        # Derived from the workbook being rendered, so v2 stays exact
        # after revisions change the fill.
        "populated_cells": sum(row["filled"] for row in rows),
    }
