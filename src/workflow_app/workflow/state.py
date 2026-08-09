"""LangGraph workflow state (plan section 30).

State stores file paths and plain values only — never in-memory objects.
This is a subset of the plan's full state shape; later tickets add
fields as their producing nodes land. Path fields are None until their
producing node has run.
"""

from typing import TypedDict


class WorkflowState(TypedDict):
    run_id: str
    workspace_path: str
    manifest_path: str | None
    schema_path: str | None
    extraction_path: str | None
    draft_xlsx_path: str | None
    review_path: str | None
    revision_path: str | None
    re_review_path: str | None
    phase: str
