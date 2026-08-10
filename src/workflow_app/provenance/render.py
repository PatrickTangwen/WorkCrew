"""Explorer data assembly (plan section 22).

Builds the language-neutral data model the review explorer embeds,
deterministically, from the draft workbook, provenance, handoff, manifest,
and optional final review-cycle artifacts. Rendering to HTML lives in
provenance/explorer.py. Workbook access goes through the writer isolation
layer (plan section 14).
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


def _evidence_data(evidence):
    return [
        {
            "file": item["source_file"],
            "location": item["source_location"],
            "text": item["evidence_text"],
            "type": item["evidence_type"],
        }
        for item in evidence
    ]


def _count_by(items, key):
    counts = {}
    for item in items:
        value = item[key]
        counts[value] = counts.get(value, 0) + 1
    return counts


def _revision_change_data(review_cycle, sheet_name):
    transitions = {}
    for mutation in review_cycle.get("revision_mutations", []):
        if mutation["sheet"] != sheet_name:
            continue
        cell_ref = writer.normalize_cell(mutation["cell"])
        if cell_ref is None:
            continue
        if cell_ref not in transitions:
            transitions[cell_ref] = {
                "before": _json_value(mutation["old_value"]),
                "after": _json_value(mutation["new_value"]),
            }
        else:
            transitions[cell_ref]["after"] = _json_value(mutation["new_value"])

    changes = {}
    for cell_ref, transition in transitions.items():
        before, after = transition["before"], transition["after"]
        if before == after:
            continue
        if before is None:
            kind = "filled"
        elif after is None:
            kind = "cleared"
        else:
            kind = "revised"
        changes[cell_ref] = {"kind": kind, **transition}

    counts = {
        "filled": sum(change["kind"] == "filled" for change in changes.values()),
        "revised": sum(change["kind"] == "revised" for change in changes.values()),
        "cleared": sum(change["kind"] == "cleared" for change in changes.values()),
        "rebutted": len(
            {
                writer.normalize_cell(decision["cell"])
                for decision in review_cycle["decisions"]
                if decision["action"] == "REBUT"
                and writer.normalize_cell(decision["cell"]) is not None
            }
        ),
    }
    return counts, changes


def _review_cycle_data(review_cycle, sheet_name):
    if review_cycle is None:
        return None, {}, {}, {}, {}, {}

    findings = {
        writer.normalize_cell(item["cell"]): {
            "verdict": item["verdict"],
            "recommended_value": item["recommended_value"],
            "comment": item["reviewer_comment"],
            "evidence": _evidence_data(item["evidence"]),
            "missed_data": item["missed_data"],
        }
        for item in review_cycle["findings"]
    }
    decisions = {
        writer.normalize_cell(item["cell"]): {
            "action": item["action"],
            "proposed_value": item["proposed_value"],
            "note_append": item["note_append"],
            "justification": item["justification"],
            "evidence": _evidence_data(item["evidence"]),
        }
        for item in review_cycle["decisions"]
    }
    verdicts = {
        writer.normalize_cell(item["cell"]): {
            "verdict": item["verdict"],
            "comment": item["reviewer_comment"],
        }
        for item in review_cycle["verdicts"]
    }
    unresolved = {
        writer.normalize_cell(item["cell"]): item["reason"]
        for item in review_cycle["unresolved"]
    }
    change_counts, changes = _revision_change_data(review_cycle, sheet_name)
    summary = {
        "verdict_counts": _count_by(review_cycle["findings"], "verdict"),
        "action_counts": _count_by(review_cycle["decisions"], "action"),
        "re_review_counts": _count_by(review_cycle["verdicts"], "verdict"),
        "unresolved_count": len(review_cycle["unresolved"]),
        "change_counts": change_counts,
    }
    return summary, findings, decisions, verdicts, unresolved, changes


def _decision_records(handoff, sheet):
    records = []
    for record in handoff.get("decision_records", []):
        record_sheet, _, cell_ref = record["cell"].rpartition("!")
        normalized = writer.normalize_cell(cell_ref)
        field = sheet.fields.get(record["column_name"])
        if (
            record_sheet != sheet.name
            or normalized is None
            or field is None
            or field.column is None
            or writer.column_of(normalized) != field.column
            or writer.row_of(normalized) != record["row"]
            or record["row"] < FIRST_DATA_ROW
        ):
            continue
        records.append((normalized, record))
    return records


def _row_numbers(book, sheet, provenance, decisions):
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
    rows.update(record["row"] for _, record in decisions)
    return sorted(rows)


def _folder_names(manifest):
    # Top-level source directories in manifest traversal order.
    names = []
    for entry in manifest.files:
        head, separator, _ = entry.path.partition("/")
        if separator and head not in names:
            names.append(head)
    return names


def _row_folders(sheet, provenance, decisions, folder_names):
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
    for _, record in decisions:
        row = record["row"]
        for evidence in record["evidence"]:
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
    # Declared duplicate merges are archival findings too (plan
    # section 22); pre-declaration handoffs carry no key.
    findings += [
        {
            "kind": "merge",
            "ref": ", ".join(merge["folders"]) + f" -> row {merge['row']}",
            "detail": merge["reason"],
        }
        for merge in handoff.get("merges", [])
    ]
    findings += [
        {"kind": "extra_review", "ref": item["cell"], "detail": item["reason"]}
        for item in handoff["extra_review"]
    ]
    return findings


def build_explorer_data(
    draft_path, schema, provenance, handoff, manifest, review_cycle=None
):
    sheet = schema.target_sheet()
    book = writer.open_draft(draft_path)
    (
        review_summary,
        findings_by_cell,
        revisions_by_cell,
        verdicts_by_cell,
        unresolved_by_cell,
        changes_by_cell,
    ) = _review_cycle_data(review_cycle, sheet.name)

    entries_by_cell = {}
    for entry in provenance["entries"]:
        entry_sheet, cell_ref = entry["cell"].split("!", 1)
        if entry_sheet == sheet.name:
            entries_by_cell[cell_ref] = entry

    decisions = _decision_records(handoff, sheet)
    proposals_by_cell = dict(decisions)
    folder_names = _folder_names(manifest)
    row_folders = _row_folders(sheet, provenance, decisions, folder_names)
    row_numbers = _row_numbers(book, sheet, provenance, decisions)
    folder_rows = {
        name: [row for row in row_numbers if name in row_folders.get(row, [])]
        for name in folder_names
    }
    # Explicit Filler merge declarations, via the handoff (ADR 0015:
    # the declaration replaced the old evidence inference and its
    # cross-citation false positives). Handoffs persisted before the
    # declaration existed carry no key. Only renderable declarations
    # get navigation markings — the surviving row must exist and the
    # folder must be a manifest folder; the handoff (and the findings
    # list) remain the faithful record of everything declared.
    declared_merges = {}
    for merge in handoff.get("merges", []):
        if merge["row"] not in row_numbers:
            continue
        for name in merge["folders"]:
            if name in folder_names:
                declared_merges[name] = {
                    "row": merge["row"],
                    "reason": merge["reason"],
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
            proposal = (
                proposals_by_cell.get(f"{spec.column}{row_number}")
                if spec.column
                else None
            )
            cell_ref = f"{spec.column}{row_number}" if spec.column else None
            fields.append(
                {
                    "name": name,
                    "column": spec.column,
                    "value": value,
                    "role": entry["agent_role"] if entry else None,
                    "pill_values": _pill_values(value, spec),
                    "gloss_zh": spec.gloss_zh,
                    "proposal": {
                        "status": proposal["status"],
                        "value": proposal["value"],
                        "confidence": proposal["confidence"],
                        "evidence": _evidence_data(proposal["evidence"]),
                        "rules_applied": proposal["rules_applied"],
                        "review_note": proposal["review_note"],
                    }
                    if proposal
                    else None,
                    "review": findings_by_cell.get(cell_ref),
                    "revision": revisions_by_cell.get(cell_ref),
                    "revision_change": changes_by_cell.get(cell_ref),
                    "re_review": verdicts_by_cell.get(cell_ref),
                    "unresolved_reason": unresolved_by_cell.get(cell_ref),
                    "sources": _evidence_data(entry["evidence"]) if entry else [],
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
                    name
                    for name, info in declared_merges.items()
                    if info["row"] == row_number
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
                "merged_into": (
                    declared_merges[name]["row"] if name in declared_merges else None
                ),
                "merge_reason": (
                    declared_merges[name]["reason"] if name in declared_merges else None
                ),
            }
            for name in folder_names
        ],
        "ungrouped_rows": [row for row in row_numbers if not row_folders.get(row)],
        "findings": _findings(handoff),
        "review_cycle": review_summary,
        "field_count": len(sheet.fields),
        # Derived from the workbook being rendered, so v2 stays exact
        # after revisions change the fill.
        "populated_cells": sum(row["filled"] for row in rows),
    }
