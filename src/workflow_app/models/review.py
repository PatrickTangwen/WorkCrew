"""Review finding, re-review verdict, and container contracts
(plan sections 18, 23, 26)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from workflow_app.models.evidence import Evidence
from workflow_app.models.values import CellValue


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: str

    verdict: Literal[
        "PASS",
        "WARN",
        "FAIL",
        "UNRESOLVED",
    ]

    issue_type: str | None = None

    current_value: CellValue = None
    recommended_value: CellValue = None

    evidence: list[Evidence]
    reviewer_comment: str

    missed_data: bool = False


class ReReviewVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell: str

    verdict: Literal[
        "WITHDRAWN",
        "UPHELD",
    ]

    reviewer_comment: str


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[ReviewFinding]


class ReReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[ReReviewVerdict]
