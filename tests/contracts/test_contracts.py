"""Contract tests: every core data contract accepts its valid fixture JSON
and rejects structurally invalid shapes (wrong enums, missing fields,
unexpected extra fields)."""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from workflow_app.models import (
    CellProposal,
    Evidence,
    ExtractionResult,
    ReReviewResult,
    ReReviewVerdict,
    ReviewFinding,
    ReviewResult,
    RevisionDecision,
    RevisionResult,
    ScopingQuestion,
    ScopingQuestions,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "contracts"
SCOPING_PROMPT = Path(__file__).parents[2] / "src/workflow_app/prompts/scoping.md"
GRAPH_SOURCE = Path(__file__).parents[2] / "src/workflow_app/workflow/graph.py"
PROGRESS_TSX = (
    Path(__file__).parents[2] / "frontend/src/components/workflow-progress.tsx"
)

CONTRACT_FIXTURES = [
    (Evidence, "evidence.json"),
    (CellProposal, "cell_proposal.json"),
    (ReviewFinding, "review_finding.json"),
    (RevisionDecision, "revision_decision.json"),
    (ReReviewVerdict, "re_review_verdict.json"),
    (ScopingQuestion, "scoping_question.json"),
]


def load(fixture_name):
    return json.loads((FIXTURES / fixture_name).read_text())


@pytest.mark.parametrize(("model", "fixture_name"), CONTRACT_FIXTURES)
def test_accepts_valid_fixture(model, fixture_name):
    instance = model.model_validate(load(fixture_name))
    # Round-trip: dumping and re-validating must be stable.
    assert model.model_validate(instance.model_dump()) == instance


@pytest.mark.parametrize(("model", "fixture_name"), CONTRACT_FIXTURES)
def test_rejects_unexpected_extra_field(model, fixture_name):
    data = load(fixture_name)
    data["unexpected_key"] = "surprise"
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_evidence_rejects_unknown_evidence_type():
    data = load("evidence.json")
    data["evidence_type"] = "hearsay"
    with pytest.raises(ValidationError):
        Evidence.model_validate(data)


def test_evidence_rejects_missing_evidence_text():
    data = load("evidence.json")
    del data["evidence_text"]
    with pytest.raises(ValidationError):
        Evidence.model_validate(data)


def test_evidence_source_location_is_optional():
    data = load("evidence.json")
    del data["source_location"]
    assert Evidence.model_validate(data).source_location is None


def test_cell_proposal_requires_explicit_value_key():
    data = load("cell_proposal.json")
    del data["value"]
    with pytest.raises(ValidationError):
        CellProposal.model_validate(data)


def test_cell_proposal_accepts_null_value():
    data = load("cell_proposal.json")
    data["value"] = None
    data["status"] = "not_found"
    data["confidence"] = None
    assert CellProposal.model_validate(data).value is None


def test_cell_proposal_rejects_unknown_status():
    data = load("cell_proposal.json")
    data["status"] = "maybe"
    with pytest.raises(ValidationError):
        CellProposal.model_validate(data)


def test_cell_proposal_rejects_numeric_confidence():
    data = load("cell_proposal.json")
    data["confidence"] = 0.93
    with pytest.raises(ValidationError):
        CellProposal.model_validate(data)


def test_cell_proposal_rejects_unknown_confidence_level():
    data = load("cell_proposal.json")
    data["confidence"] = "very_high"
    with pytest.raises(ValidationError):
        CellProposal.model_validate(data)


def test_cell_proposal_schema_exposes_only_categorical_confidence():
    confidence = CellProposal.model_json_schema()["properties"]["confidence"]
    branches = confidence["anyOf"]

    assert any(
        set(branch.get("enum", [])) == {"low", "medium", "high"} for branch in branches
    )
    assert any(branch.get("type") == "null" for branch in branches)


def test_proposed_cell_requires_a_confidence_level():
    data = load("cell_proposal.json")
    data["confidence"] = None
    with pytest.raises(ValidationError, match="proposed"):
        CellProposal.model_validate(data)


@pytest.mark.parametrize("status", ["not_found", "ambiguous", "conflict"])
def test_non_proposed_cell_requires_null_confidence(status):
    data = load("cell_proposal.json")
    data["value"] = None
    data["status"] = status
    with pytest.raises(ValidationError, match="non-proposed"):
        CellProposal.model_validate(data)

    data["confidence"] = None
    assert CellProposal.model_validate(data).confidence is None


def test_cell_proposal_rejects_malformed_nested_evidence():
    data = load("cell_proposal.json")
    data["evidence"] = [{"source_file": "brief.pdf"}]
    with pytest.raises(ValidationError):
        CellProposal.model_validate(data)


def test_review_finding_rejects_lowercase_verdict():
    data = load("review_finding.json")
    data["verdict"] = "warn"
    with pytest.raises(ValidationError):
        ReviewFinding.model_validate(data)


def test_review_finding_missed_data_defaults_to_false():
    data = load("review_finding.json")
    del data["missed_data"]
    assert ReviewFinding.model_validate(data).missed_data is False


def test_revision_decision_rejects_unknown_action():
    data = load("revision_decision.json")
    data["action"] = "IGNORE"
    with pytest.raises(ValidationError):
        RevisionDecision.model_validate(data)


def test_revision_decision_rejects_missing_justification():
    data = load("revision_decision.json")
    del data["justification"]
    with pytest.raises(ValidationError):
        RevisionDecision.model_validate(data)


def test_re_review_verdict_rejects_unknown_verdict():
    data = load("re_review_verdict.json")
    data["verdict"] = "PARTIAL"
    with pytest.raises(ValidationError):
        ReReviewVerdict.model_validate(data)


def test_extraction_result_wraps_proposals():
    container = {"proposals": [load("cell_proposal.json")]}
    result = ExtractionResult.model_validate(container)
    assert len(result.proposals) == 1


def test_scoping_question_rejects_missing_question_text():
    data = load("scoping_question.json")
    del data["question"]
    with pytest.raises(ValidationError):
        ScopingQuestion.model_validate(data)


def test_scoping_question_defaults_legacy_payloads_to_text():
    question = ScopingQuestion.model_validate(load("scoping_question.json"))

    assert question.type == "text"
    assert question.options is None


def test_scoping_question_accepts_typed_options():
    question = ScopingQuestion.model_validate(
        {
            "id": "Q2",
            "question": "Which folders belong to the 2026 cohort?",
            "type": "multi_select",
            "options": [
                {"value": "alpha", "label": "Alpha folder"},
                {"value": "beta", "label": "Beta folder"},
            ],
        }
    )

    assert question.type == "multi_select"
    assert [option.value for option in question.options] == ["alpha", "beta"]


def test_scoping_question_rejects_unknown_type():
    data = load("scoping_question.json")
    data["type"] = "dropdown"

    with pytest.raises(ValidationError):
        ScopingQuestion.model_validate(data)


def test_scoping_prompt_requests_typed_questions():
    prompt = SCOPING_PROMPT.read_text()

    assert all(
        f"`{question_type}`" in prompt
        for question_type in ("text", "single_select", "multi_select", "confirm")
    )
    assert '"options": [{"value":' in prompt
    assert "defaults to `text`" in prompt


@pytest.mark.parametrize(
    ("model", "key", "fixture_name"),
    [
        (ReviewResult, "findings", "review_finding.json"),
        (RevisionResult, "decisions", "revision_decision.json"),
        (ReReviewResult, "verdicts", "re_review_verdict.json"),
        (ScopingQuestions, "questions", "scoping_question.json"),
    ],
)
def test_result_containers_wrap_their_items(model, key, fixture_name):
    result = model.model_validate({key: [load(fixture_name)]})
    assert len(getattr(result, key)) == 1
    with pytest.raises(ValidationError):
        model.model_validate({})
    with pytest.raises(ValidationError):
        model.model_validate({key: [], "extra": True})


def test_extraction_result_requires_proposals_key():
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate({})


def test_extraction_result_rejects_extra_keys():
    container = {"proposals": [], "summary": "chatty agent prose"}
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(container)


def test_every_engine_stage_maps_to_a_ui_pipeline_stage():
    # The UI falls back to stage 0 for an unrecognized phase, so a stage
    # added to the graph but not to the map silently reports its failures
    # against Scoping.
    stages = set(
        re.findall(r'graph\.add_node\(\s*"([A-Z_]+)"', GRAPH_SOURCE.read_text())
    )
    mapped = set(
        re.findall(r"^\s*([A-Z_]+): \d+,$", PROGRESS_TSX.read_text(), re.MULTILINE)
    )

    assert stages, "no graph stages found; the add_node scan needs updating"
    assert stages <= mapped, (
        f"stages missing from the UI phase map: {sorted(stages - mapped)}"
    )


def test_scoping_prompt_pins_the_strptime_date_format():
    prompt = " ".join(SCOPING_PROMPT.read_text().split())

    assert "Python strptime pattern" in prompt
    assert "`%Y-%m-%d`" in prompt
    assert "never the human-readable `YYYY-MM-DD`" in prompt


def test_scoping_prompt_makes_the_row_mapping_mandatory():
    # The first writable row lives nowhere in the schema, so the pass has
    # to establish it or the extraction overwrites the header row.
    # Flattened because the prompt is wrapped markdown.
    prompt = " ".join(SCOPING_PROMPT.read_text().split())

    assert "row mapping is mandatory" in prompt.lower()
    assert "state the first writable row explicitly" in prompt
    assert "Never assume the header is row 1." in prompt
