"""Revision decision contract (plan section 18)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.models.evidence import Evidence


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

    original_value: Any | None = None
    proposed_value: Any | None = None

    note_append: str | None = None

    evidence: list[Evidence]
    justification: str
