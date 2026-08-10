"""Live Claude Code runtime smoke tests (ticket #10, plan section 41).

These spend real subscription quota and are excluded from the default
test run; execute them with `pytest -m smoke`. Each test plants
intentionally invalid API-billing credentials in the parent
environment: the live call can only succeed if the adapter cleared
them for the child process and subscription auth took over.
"""

import json
from pathlib import Path

import pytest

from workflow_app.models.extraction import ExtractionResult
from workflow_app.models.scoping import ScopingQuestions
from workflow_app.runtimes.base import AgentResult
from workflow_app.runtimes.claude_code import ClaudeCodeRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs, Workspace

pytestmark = pytest.mark.smoke

# Fields capped at medium confidence (constructed / mapped, ADR 0024)
# in the sample workspace's schema config.
CAPPED_FIELDS = {"Project ID*", "Maturity"}


class AllClearReviewerRuntime:
    name = "fake"

    def run(self, request):
        inputs_path = (
            Path(request.workspace_path) / "agent_outputs/reviewer/inputs.json"
        )
        targets = json.loads(inputs_path.read_text())["review_targets"]
        findings = [
            {
                "cell": target["cell"],
                "verdict": "PASS",
                "evidence": [],
                "reviewer_comment": "Covered by the deterministic review plan.",
            }
            for target in targets
        ]
        return AgentResult(status="ok", output={"findings": findings})


def live_runtimes():
    claude = ClaudeCodeRuntime()
    return {
        "scoping": claude,
        "filler": claude,
        "reviewer": AllClearReviewerRuntime(),
    }


def run_inputs(inputs, scoping_answers=None):
    return RunInputs(
        source=inputs["source"],
        workbook=inputs["workbook"],
        rules=inputs["rules"],
        workbook_schema=inputs["workbook_schema"],
        scoping_answers=scoping_answers,
    )


def test_live_scoping_pass(inputs, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid-cleared-by-adapter")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "invalid-cleared-by-adapter")

    state = run_workflow(
        inputs=run_inputs(inputs),
        runs_root=inputs["runs_root"],
        runtimes=live_runtimes(),
    )

    # The run paused for answers after the live scoping pass.
    assert "__interrupt__" in state
    workspace = Workspace(Path(state["workspace_path"]))

    questions = ScopingQuestions.model_validate_json(
        workspace.scoping_questions_json.read_text()
    )
    assert questions.questions, "live scoping produced no questions"
    for question in questions.questions:
        assert question.id.strip()
        # Plausible questions are actual sentences, not placeholders.
        assert len(question.question.strip()) > 15

    # The raw structured output landed under the filler actor directory
    # (ADR 0014) and the result envelope was captured for audit.
    assert (workspace.filler_outputs / "scoping_questions.json").is_file()
    envelope = json.loads(
        (workspace.root / "logs" / "claude_scoping_result.json").read_text()
    )
    assert envelope["is_error"] is False

    err = capsys.readouterr().err
    assert "Claude Code auth: OAuth (subscription - best effort)" in err
    assert "API key env vars: cleared (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN)" in err
    assert "cannot be verified" in err


def test_live_fill(inputs, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-invalid-cleared-by-adapter")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "invalid-cleared-by-adapter")

    # Pre-provided answers skip the scoping pause (plan section 20).
    state = run_workflow(
        inputs=run_inputs(inputs, scoping_answers=inputs["scoping_answers"]),
        runs_root=inputs["runs_root"],
        runtimes=live_runtimes(),
    )

    assert "__interrupt__" not in state
    workspace = Workspace(Path(state["workspace_path"]))

    extraction = ExtractionResult.model_validate_json(
        (workspace.filler_outputs / "extraction.json").read_text()
    )
    assert extraction.proposals, "live fill produced no proposals"

    # The capped fields must actually be proposed — otherwise the cap
    # assertion below could pass vacuously on an empty-handed fill.
    proposed_fields = {
        proposal.column_name
        for proposal in extraction.proposals
        if proposal.status == "proposed"
    }
    assert CAPPED_FIELDS <= proposed_fields, (
        f"live fill did not propose the capped fields: {proposed_fields}"
    )

    for proposal in extraction.proposals:
        # Contract validity (types, evidence_type tags) is enforced by
        # model_validate above; assert the semantic policies on top.
        if proposal.status == "proposed":
            assert proposal.evidence, (
                f"proposed cell {proposal.cell} carries no evidence"
            )
        if proposal.column_name in CAPPED_FIELDS:
            assert proposal.confidence in {"low", "medium"}, (
                f"{proposal.column_name} is constructed/mapped but has "
                f"confidence {proposal.confidence}"
            )

    # The pipeline consumed the extraction through to the final workbook
    # (fake all-clear review short-circuits to FINALIZE).
    assert workspace.draft_xlsx.is_file()
    assert workspace.final_xlsx.is_file()
