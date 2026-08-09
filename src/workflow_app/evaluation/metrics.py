"""Evaluation metric core (ticket #13, plan section 42).

Pure computation over benchmark labels plus the facts extracted from a
completed run: final cell values, the filler's draft values, the
provenance log, review findings, revision decisions, and the
unresolved set. Ratios report numerator and denominator alongside the
value; an empty denominator yields None, never a fake zero.
"""

import datetime
import re
from decimal import Decimal
from pathlib import PurePosixPath

NUMERIC = re.compile(r"-?\d+(\.\d+)?")

PRIMARY_EDITS = ("ACCEPT", "FIX", "CLEAR")


def normalize_value(value):
    # Comparison form shared by labels and workbook values: numbers to
    # two decimals (the dataset's amount convention), dates to ISO,
    # strings to the dataset's underscore style, case-insensitive.
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.date().isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).casefold()
    if isinstance(value, (int, float, Decimal)):
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    text = str(value).strip()
    if not text:
        return None
    if NUMERIC.fullmatch(text):
        return str(Decimal(text).quantize(Decimal("0.01")))
    return text.replace(" ", "_").replace(":", "_").casefold()


def _rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": None if denominator == 0 else numerator / denominator,
    }


def _cites_folder(entry, folder):
    return any(
        folder in PurePosixPath(evidence["source_file"]).parts
        for evidence in entry["evidence"]
    )


def compute_metrics(
    labels, final_cells, draft_cells, provenance, findings, decisions, unresolved_cells
):
    provenance_by_cell = {
        entry["cell"].rsplit("!", 1)[1]: entry for entry in provenance
    }
    flagged = {finding["cell"] for finding in findings if finding["verdict"] != "PASS"}
    escalated = set(unresolved_cells)

    details = []
    label_by_cell = {}
    counts = {
        "expected": 0,
        "accurate": 0,
        "missed": 0,
        "blank": 0,
        "unsupported": 0,
        "filled": 0,
        "covered": 0,
        "draft_wrong": 0,
        "draft_wrong_flagged": 0,
        "draft_correct": 0,
        "draft_correct_flagged": 0,
        "labeled_unresolved": 0,
        "labeled_unresolved_escalated": 0,
    }

    for row in labels.rows:
        for field_name, label in row.fields.items():
            cell = label.cell
            label_by_cell[cell] = label
            expected_norm = normalize_value(label.expected_value)
            final_norm = normalize_value(final_cells.get(cell))
            draft_norm = normalize_value(draft_cells.get(cell))

            if label.status == "expected":
                final_correct = final_norm == expected_norm
                draft_correct = draft_norm == expected_norm
                counts["expected"] += 1
                counts["accurate"] += final_correct
                counts["missed"] += final_norm is None
            else:
                # blank and unresolved: the correct cell state is empty.
                final_correct = final_norm is None
                draft_correct = draft_norm is None
                if label.status == "blank":
                    counts["blank"] += 1
                    counts["unsupported"] += final_norm is not None
                else:
                    counts["labeled_unresolved"] += 1
                    counts["labeled_unresolved_escalated"] += cell in escalated

            if final_norm is not None:
                counts["filled"] += 1
                entry = provenance_by_cell.get(cell)
                counts["covered"] += entry is not None and _cites_folder(
                    entry, row.folder
                )

            if draft_correct:
                counts["draft_correct"] += 1
                counts["draft_correct_flagged"] += cell in flagged
            else:
                counts["draft_wrong"] += 1
                counts["draft_wrong_flagged"] += cell in flagged

            details.append(
                {
                    "cell": cell,
                    "field": field_name,
                    "row": row.row,
                    "folder": row.folder,
                    "status": label.status,
                    "expected_value": label.expected_value,
                    "draft_value": draft_cells.get(cell),
                    "final_value": final_cells.get(cell),
                    "draft_correct": draft_correct,
                    "final_correct": final_correct,
                    "flagged": cell in flagged,
                    "escalated": cell in escalated,
                }
            )

    revision_total, revision_correct = 0, 0
    final_correct_by_cell = {item["cell"]: item["final_correct"] for item in details}
    for decision in decisions:
        cell = decision["cell"]
        if decision["action"] in PRIMARY_EDITS and cell in label_by_cell:
            revision_total += 1
            revision_correct += final_correct_by_cell[cell]

    evidence_total = sum(len(entry["evidence"]) for entry in provenance)
    evidence_web = sum(
        1
        for entry in provenance
        for evidence in entry["evidence"]
        if evidence["evidence_type"] == "external_web"
    )

    metrics = {
        "field_accuracy": _rate(counts["accurate"], counts["expected"]),
        "missed_data_rate": _rate(counts["missed"], counts["expected"]),
        "unsupported_fill_rate": _rate(counts["unsupported"], counts["blank"]),
        "provenance_coverage": _rate(counts["covered"], counts["filled"]),
        "review_true_positive_rate": _rate(
            counts["draft_wrong_flagged"], counts["draft_wrong"]
        ),
        "review_false_positive_rate": _rate(
            counts["draft_correct_flagged"], counts["draft_correct"]
        ),
        "revision_correctness": _rate(revision_correct, revision_total),
        "unresolved_count": len(escalated),
        "expected_unresolved_escalated": _rate(
            counts["labeled_unresolved_escalated"], counts["labeled_unresolved"]
        ),
        "web_evidence_percentage": _rate(evidence_web, evidence_total),
    }
    return {
        "benchmark": labels.benchmark,
        "sheet": labels.sheet,
        "metrics": metrics,
        "cells": details,
    }
