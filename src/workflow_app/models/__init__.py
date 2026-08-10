"""Core data contracts (plan section 18)."""

from workflow_app.models.confidence import ConfidenceLevel
from workflow_app.models.evidence import Evidence
from workflow_app.models.extraction import CellProposal, ExtractionResult, FolderMerge
from workflow_app.models.review import (
    ReReviewResult,
    ReReviewVerdict,
    ReviewFinding,
    ReviewResult,
)
from workflow_app.models.revision import RevisionDecision, RevisionResult
from workflow_app.models.scoping import ScopingQuestion, ScopingQuestions
from workflow_app.models.values import CellValue

__all__ = [
    "CellProposal",
    "CellValue",
    "ConfidenceLevel",
    "Evidence",
    "ExtractionResult",
    "FolderMerge",
    "ReReviewResult",
    "ReReviewVerdict",
    "ReviewFinding",
    "ReviewResult",
    "RevisionDecision",
    "RevisionResult",
    "ScopingQuestion",
    "ScopingQuestions",
]
