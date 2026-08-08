"""LangGraph workflow state (plan section 30).

State stores file paths and plain values only — never in-memory objects.
Ticket #2 carries the walking-skeleton subset of the full state shape;
later tickets add fields as their producing nodes land.
"""

from typing import TypedDict


class WorkflowState(TypedDict):
    run_id: str
    workspace_path: str
    extraction_path: str | None
    phase: str
