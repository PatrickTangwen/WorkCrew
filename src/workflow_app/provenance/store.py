"""Cell-level provenance records (plan section 19).

Machine-readable JSON is the authoritative provenance record; one entry
per applied workbook mutation, carrying the evidence and confidence of
the proposal that produced it.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

from workflow_app.models import Evidence
from workflow_app.workbook.safety import cell_key


class ProvenanceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: str  # "<sheet>!<CELL>"
    value: Any
    agent_role: str
    agent_runtime: str
    evidence: list[Evidence]
    rules_applied: list[str]
    # Revision decisions carry no confidence score (plan section 18),
    # so revision-authored entries record None.
    confidence: float | None
    run_id: str


class ProvenanceLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[ProvenanceEntry]


def build_provenance(applied, run_id, agent_role, agent_runtime):
    # applied: (proposal, normalized cell ref) pairs actually written.
    entries = [
        ProvenanceEntry(
            cell=cell_key(proposal.sheet, cell_ref),
            value=proposal.value,
            agent_role=agent_role,
            agent_runtime=agent_runtime,
            evidence=proposal.evidence,
            rules_applied=proposal.rules_applied,
            confidence=proposal.confidence,
            run_id=run_id,
        )
        for proposal, cell_ref in applied
    ]
    return ProvenanceLog(entries=entries)
