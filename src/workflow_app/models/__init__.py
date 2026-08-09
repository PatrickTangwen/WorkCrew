"""Core data contracts (plan section 18)."""

from workflow_app.models.evidence import Evidence
from workflow_app.models.extraction import CellProposal, ExtractionResult
from workflow_app.models.review import (
    ReReviewResult,
    ReReviewVerdict,
    ReviewFinding,
    ReviewResult,
)
from workflow_app.models.revision import RevisionDecision, RevisionResult
from workflow_app.models.scoping import ScopingQuestion, ScopingQuestions

__all__ = [
    "CellProposal",
    "Evidence",
    "ExtractionResult",
    "ReReviewResult",
    "ReReviewVerdict",
    "ReviewFinding",
    "ReviewResult",
    "RevisionDecision",
    "RevisionResult",
    "ScopingQuestion",
    "ScopingQuestions",
]
