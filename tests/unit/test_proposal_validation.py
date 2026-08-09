"""Proposal-level validation rules (ticket #5, plan sections 20, 25).

check_proposal enforces the medium-confidence cap for constructed and
mapped fields and schema consistency; classify_confidence buckets
confidence with the spec thresholds (low < 0.60 <= medium < 0.85 <= high).
"""

import pytest

from workflow_app.models import CellProposal
from workflow_app.validation.rules import (
    HIGH_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    check_proposal,
    classify_confidence,
)
from workflow_app.workbook.schema import WorkbookSchema

SHEET = "7) Practicum Courses"

SCHEMA = WorkbookSchema.model_validate(
    {
        "sheets": [
            {
                "name": SHEET,
                "target": True,
                "fields": {
                    "Project ID*": {
                        "required": True,
                        "type": "id",
                        "column": "A",
                        "pattern": r"^PRJ-\d{4}$",
                        "value_kind": "constructed",
                        "writable": True,
                    },
                    "Main Issue Area(s)": {
                        "type": "controlled_vocabulary",
                        "column": "G",
                        "values": ["Healthcare", "Education"],
                        "writable": True,
                    },
                    "Maturity": {
                        "type": "string",
                        "column": "E",
                        "value_kind": "mapped",
                        "writable": True,
                    },
                    "Notes": {"type": "string", "column": "F", "writable": True},
                },
            }
        ]
    }
)


def proposal(**overrides):
    base = {
        "sheet": SHEET,
        "row": 12,
        "column_name": "Notes",
        "cell": "F12",
        "value": "A sourced note.",
        "evidence": [
            {
                "source_file": "India 2008/brief.pdf",
                "evidence_text": "…",
                "evidence_type": "direct",
            }
        ],
        "rules_applied": [],
        "confidence": 0.95,
        "status": "proposed",
    }
    base.update(overrides)
    return CellProposal.model_validate(base)


# --- confidence buckets --------------------------------------------------


@pytest.mark.parametrize(
    ("confidence", "bucket"),
    [
        (0.0, "low"),
        (0.59, "low"),
        (LOW_CONFIDENCE_THRESHOLD, "medium"),
        (0.7, "medium"),
        (0.84, "medium"),
        (HIGH_CONFIDENCE_THRESHOLD, "high"),
        (1.0, "high"),
    ],
)
def test_classify_confidence_buckets(confidence, bucket):
    assert classify_confidence(confidence) == bucket


# --- the medium-confidence cap ------------------------------------------


def test_free_field_may_be_high_confidence():
    assert check_proposal(proposal(), SCHEMA) is None


@pytest.mark.parametrize(
    ("column_name", "cell", "value"),
    [
        ("Project ID*", "A12", "PRJ-0001"),  # constructed
        ("Maturity", "E12", "Established"),  # mapped by value_kind
        ("Main Issue Area(s)", "G12", "Healthcare"),  # mapped by type
    ],
)
def test_constructed_and_mapped_fields_are_capped_at_medium(column_name, cell, value):
    capped = proposal(
        column_name=column_name,
        cell=cell,
        value=value,
        confidence=HIGH_CONFIDENCE_THRESHOLD,
    )
    reason = check_proposal(capped, SCHEMA)
    assert reason is not None and "medium" in reason


def test_capped_field_passes_below_the_threshold():
    ok = proposal(column_name="Maturity", cell="E12", value="Emerging", confidence=0.84)
    assert check_proposal(ok, SCHEMA) is None


# --- schema consistency --------------------------------------------------


def test_unknown_sheet_is_rejected():
    reason = check_proposal(proposal(sheet="Ghost"), SCHEMA)
    assert reason is not None and "sheet" in reason


def test_unknown_column_name_is_rejected():
    reason = check_proposal(proposal(column_name="Imaginary"), SCHEMA)
    assert reason is not None and "field" in reason


def test_cell_in_wrong_column_is_rejected():
    reason = check_proposal(proposal(cell="G12"), SCHEMA)
    assert reason is not None and "column" in reason


def test_cell_row_must_match_declared_row():
    reason = check_proposal(proposal(cell="F13"), SCHEMA)
    assert reason is not None and "row" in reason


def test_malformed_cell_address_is_rejected():
    reason = check_proposal(proposal(cell="12F"), SCHEMA)
    assert reason is not None and "address" in reason
