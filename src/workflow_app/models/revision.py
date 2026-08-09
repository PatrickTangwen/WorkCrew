"""Revision decision contract (plan section 18)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.models.evidence import Evidence
from workflow_app.models.values import CellValue


class RevisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: str

    action: Literal[
        "ACCEPT",
        "FIX",
        "REBUT",
        "CLEAR",
        "NO_CHANGE",
        "UNRESOLVED",
    ]

    original_value: CellValue = None
    proposed_value: CellValue = None

    note_append: str | None = None

    evidence: list[Evidence]
    justification: str


class RevisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[RevisionDecision]
