"""Handoff report generation (plan sections 21, 22).

Deterministically summarizes the fill for the Reviewer and the human:
processed and unreadable sources, confidence distribution, uncertainty
statuses, and areas recommended for extra review. handoff.json is the
machine artifact; handoff.md is its human rendering.
"""

from collections import Counter

from workflow_app.workbook.safety import cell_key


def build_handoff(manifest, extraction, rejections, outcomes, schema):
    proposals = extraction.proposals
    proposed = [p for p in proposals if p.status == "proposed"]
    applied = [o for o in outcomes if o.status == "applied"]
    safety_rejected = [o for o in outcomes if o.status == "rejected"]

    confidence = Counter(p.confidence for p in proposed)
    evidence_types = Counter(
        item.evidence_type for p in proposals for item in p.evidence
    )

    extra_review = (
        [
            {"cell": rejection["cell"], "reason": rejection["reason"]}
            for rejection in rejections
        ]
        + [
            {
                "cell": cell_key(o.mutation.sheet, o.cell_ref),
                "reason": o.reason,
            }
            for o in safety_rejected
        ]
        + [
            {
                "cell": cell_key(p.sheet, p.cell),
                "reason": "written at low confidence",
            }
            for p in proposed
            if p.confidence == "low" and _was_applied(p, applied)
        ]
    )

    return {
        "sources": {
            "total": len(manifest.files),
            "readable": sum(1 for f in manifest.files if f.status == "ok"),
            "unreadable": [
                {"path": f.path, "status": f.status}
                for f in manifest.files
                if f.status != "ok"
            ],
        },
        "records_evaluated": len({(p.sheet, p.row) for p in proposals}),
        "populated_cells": len(applied),
        "confidence_distribution": {
            "low": confidence.get("low", 0),
            "medium": confidence.get("medium", 0),
            "high": confidence.get("high", 0),
        },
        "evidence_summary": dict(sorted(evidence_types.items())),
        "decision_records": [_decision_record(p) for p in proposals],
        "missing_fields": [
            {
                "cell": cell_key(p.sheet, p.cell),
                "column_name": p.column_name,
                "required": _is_required(p, schema),
            }
            for p in proposals
            if p.status == "not_found"
        ],
        "ambiguities": _uncertainty(proposals, "ambiguous"),
        "source_conflicts": _uncertainty(proposals, "conflict"),
        "extra_review": extra_review,
        # Explicit duplicate-folder declarations (ADR 0015): the
        # explorer renders these instead of inferring merges.
        "merges": [merge.model_dump() for merge in extraction.merges],
    }


def _was_applied(proposal, applied):
    cell = cell_key(proposal.sheet, proposal.cell)
    return any(cell_key(o.mutation.sheet, o.cell_ref) == cell for o in applied)


def _is_required(proposal, schema):
    sheet = schema.sheet_named(proposal.sheet)
    field = sheet.fields.get(proposal.column_name) if sheet else None
    return bool(field and field.required)


def _uncertainty(proposals, status):
    return [
        {
            "cell": cell_key(p.sheet, p.cell),
            "column_name": p.column_name,
            "notes": p.notes,
        }
        for p in proposals
        if p.status == status
    ]


def _decision_record(proposal):
    review_note = proposal.notes
    if review_note is None and proposal.status == "proposed":
        rules = ", ".join(proposal.rules_applied)
        if proposal.confidence == "low":
            review_note = "verify weak supporting evidence before acceptance"
        elif proposal.confidence == "medium" and rules:
            review_note = f"verify rule application: {rules}"
        elif proposal.confidence == "medium":
            review_note = "verify the evidence-supported transformation or mapping"
        else:
            review_note = "confirm exact supporting evidence and target ownership"
    if review_note is None and proposal.status != "proposed":
        review_note = f"{proposal.status} proposal"
    return {
        "cell": cell_key(proposal.sheet, proposal.cell),
        "row": proposal.row,
        "column_name": proposal.column_name,
        "status": proposal.status,
        "value": proposal.value,
        "confidence": proposal.confidence,
        "evidence": [item.model_dump() for item in proposal.evidence],
        "rules_applied": proposal.rules_applied,
        "review_note": review_note,
    }


def _markdown_cell(value):
    if value is None:
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_handoff_markdown(handoff):
    sources = handoff["sources"]
    lines = [
        "# Fill handoff",
        "",
        "## Sources",
        "",
        f"- Files: {sources['total']} total, {sources['readable']} readable",
    ]
    for item in sources["unreadable"]:
        lines.append(f"- Unreadable: {item['path']} ({item['status']})")
    lines += [
        "",
        "## Fill",
        "",
        f"- Records evaluated: {handoff['records_evaluated']}",
        f"- Cells populated: {handoff['populated_cells']}",
        "",
        "## Confidence distribution",
        "",
    ]
    for bucket in ("low", "medium", "high"):
        lines.append(f"- {bucket}: {handoff['confidence_distribution'][bucket]}")
    lines += ["", "## Evidence types", ""]
    for evidence_type, count in handoff["evidence_summary"].items():
        lines.append(f"- {evidence_type}: {count}")

    lines += ["", "## Decision ledger", ""]
    current_group = None
    for item in handoff["decision_records"]:
        sheet_name, _ = item["cell"].split("!", 1)
        group = (sheet_name, item["row"])
        if group != current_group:
            if current_group is not None:
                lines.append("")
            lines += [
                f"### {sheet_name} — row {item['row']}",
                "",
                "| Cell | Field | Status | Value | Confidence | Evidence | Review note |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            current_group = group
        evidence_parts = [
            source["source_file"]
            + (f" ({source['source_location']})" if source["source_location"] else "")
            + f" [{source['evidence_type']}] — {source['evidence_text']}"
            for source in item["evidence"]
        ]
        rules = ", ".join(item["rules_applied"])
        if rules:
            evidence_parts.append(f"rule: {rules}")
        evidence = "\n".join(evidence_parts)
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    item["cell"],
                    item["column_name"],
                    item["status"],
                    item["value"],
                    item["confidence"],
                    evidence,
                    item["review_note"],
                )
            )
            + " |"
        )

    for title, key in (
        ("Missing fields", "missing_fields"),
        ("Ambiguities", "ambiguities"),
        ("Source conflicts", "source_conflicts"),
    ):
        lines += ["", f"## {title}", ""]
        if not handoff[key]:
            lines.append("- none")
        for item in handoff[key]:
            note = item.get("notes") or ""
            suffix = f" — {note}" if note else ""
            lines.append(f"- {item['cell']} ({item['column_name']}){suffix}")

    lines += ["", "## Declared duplicate merges", ""]
    if not handoff["merges"]:
        lines.append("- none")
    for merge in handoff["merges"]:
        folders = ", ".join(merge["folders"])
        lines.append(f"- {folders} -> row {merge['row']}: {merge['reason']}")

    lines += ["", "## Recommended for extra review", ""]
    if not handoff["extra_review"]:
        lines.append("- none")
    for item in handoff["extra_review"]:
        lines.append(f"- {item['cell']}: {item['reason']}")
    lines.append("")
    return "\n".join(lines)
