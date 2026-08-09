"""Cell proposal and extraction container contracts (plan sections 18, 21)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.models.evidence import Evidence
from workflow_app.models.values import CellValue


class CellProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: str
    row: int
    column_name: str
    cell: str

    value: CellValue

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


class FolderMerge(BaseModel):
    """Explicit duplicate-folder declaration (ADR 0015): the named
    source folders describe the same entity as the surviving row."""

    model_config = ConfigDict(extra="forbid")

    folders: list[str]
    row: int
    reason: str


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposals: list[CellProposal]
    # Default keeps every pre-declaration extraction artifact valid.
    merges: list[FolderMerge] = []
