"""Cell proposal and extraction container contracts (plan sections 18, 21)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.models.evidence import Evidence


class CellProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: str
    row: int
    column_name: str
    cell: str

    value: Any | None

    evidence: list[Evidence]
    rules_applied: list[str]

    confidence: float

    status: Literal[
        "proposed",
        "not_found",
        "ambiguous",
        "conflict",
    ]

    notes: str | None = None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[CellProposal]
