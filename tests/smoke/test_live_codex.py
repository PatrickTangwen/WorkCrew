"""Live Codex runtime smoke tests (ticket #11, plan section 41).

These spend real Codex subscription quota and are excluded from the
default run; execute them with `pytest -m smoke`. The Filler side is
fake (no Claude quota): live review runs against a fake-filler draft.
Each test plants intentionally invalid Codex API env credentials in
the parent environment: the live call can only succeed if the adapter
cleared them and auth.json subscription auth took over.
"""

import hashlib
import json
from pathlib import Path

import pytest

from workflow_app.models.review import ReReviewResult, ReviewResult
from workflow_app.runtimes.base import AgentResult
from workflow_app.runtimes.codex import CodexRuntime
from workflow_app.runtimes.fake import FakeAgentRuntime
from workflow_app.workflow.engine import run_workflow
from workflow_app.workspace import RunInputs, Workspace

pytestmark = pytest.mark.smoke

SHEET = "7) Practicum Courses"
BRIEF_PATH = "India 2008/Project_Brief.txt"

POLICY_YAML = (
    "review:\n"
    "  strict_fields:\n"
    "    - 'Project ID*'\n"
    "    - Start Date\n"
    "  high_confidence_sampling_per_record: 2\n"
)


def evidence(text):
    return {
        "source_file": BRIEF_PATH,
        "source_location": None,
        "evidence_text": text,
        "evidence_type": "direct",
    }


def proposal(column_name, cell, value, confidence, text):
    return {
        "sheet": SHEET,
        "row": 2,
        "column_name": column_name,
        "cell": cell,
        "value": value,
        "evidence": [evidence(text)],
        "rules_applied": ["extraction_rules"],
        "confidence": confidence,
        "status": "proposed",
        "notes": None,
    }


def filler_fixture(start_date):
    # One row from the brief; start_date is where a test can plant a
    # deliberate error for the live Reviewer to catch.
    return {
        "proposals": [
            proposal(
                "Project ID*",
                "A2",
                "PRJ-2008",
                "medium",
                "began operations on 2008-03-15",
            ),
            proposal(
                "Start Date",
                "D2",
                start_date,
                "high",
                "began operations on 2008-03-15",
            ),
            proposal(
                "Maturity",
                "E2",
                "Established",
                "medium",
                "the team considered the program well established",
            ),
            proposal(
                "Main Issue Area(s)",
                "G2",
                "Healthcare",
                "medium",
                "Primary focus: community healthcare delivery.",
            ),
        ]
    }


def sha256_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class HashObservingRuntime:
    """Wraps a live runtime; records the draft hash on both sides of
    every call, so mutation-freedom is asserted exactly around the
    agent invocation."""

    def __init__(self, inner):
        self._inner = inner
        self.name = inner.name
        self.observations = {}

    def run(self, request):
        draft = Path(request.workspace_path) / "working" / "draft.xlsx"
        before = sha256_of(draft)
        result = self._inner.run(request)
        self.observations[request.role] = (before, sha256_of(draft))
        return result


class AdaptiveRevisionFake:
    """Test fixture: answers whatever the live review returned, so the
    run always routes to completion. WARN findings are accepted when a
    recommendation exists (rebutted otherwise); everything else defers
    to human review."""

    name = "fake"

    def run(self, request):
        review = json.loads(
            (Path(request.workspace_path) / "artifacts" / "review.json").read_text()
        )
        decisions = []
        for finding in review["findings"]:
            if finding["verdict"] == "PASS":
                continue
            if finding["verdict"] == "WARN":
                if finding.get("recommended_value") is not None:
                    action = "ACCEPT"
                    justification = "Adopting the Reviewer's recommendation."
                else:
                    action = "REBUT"
                    justification = (
                        "The brief supports the drafted value; see the cited text."
                    )
            else:
                action = "UNRESOLVED"
                justification = "Deferred to human review by the smoke fixture."
            decisions.append(
                {
                    "cell": finding["cell"],
                    "action": action,
                    "original_value": finding.get("current_value"),
                    "proposed_value": None,
                    "note_append": None,
                    "evidence": [evidence("began operations on 2008-03-15")],
                    "justification": justification,
                }
            )
        return AgentResult(status="ok", output={"decisions": decisions})


def plant_invalid_credentials(monkeypatch):
    # Before the runtime is constructed, so the startup diagnostic sees
    # (and reports clearing) the planted credentials.
    monkeypatch.setenv("CODEX_API_KEY", "sk-invalid-cleared-by-adapter")
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "invalid-cleared-by-adapter")


def start_run(inputs, tmp_path, runtimes, filler):
    policy = tmp_path / "review_policy.yaml"
    policy.write_text(POLICY_YAML)
    return run_workflow(
        inputs=RunInputs(
            source=inputs["source"],
            workbook=inputs["workbook"],
            rules=inputs["rules"],
            workbook_schema=inputs["workbook_schema"],
            scoping_answers=inputs["scoping_answers"],
            review_policy=policy,
        ),
        runs_root=inputs["runs_root"],
        runtimes={"filler": FakeAgentRuntime({"filler": filler}), **runtimes},
    )


def test_live_review_of_fake_filler_draft(inputs, tmp_path, monkeypatch, capsys):
    plant_invalid_credentials(monkeypatch)
    codex = HashObservingRuntime(CodexRuntime())
    state = start_run(
        inputs,
        tmp_path,
        {"reviewer": codex, "revision": AdaptiveRevisionFake(), "re_review": codex},
        # Planted error: the brief says operations began on 2008-03-15.
        filler_fixture(start_date="2007-01-01"),
    )
    workspace = Workspace(Path(state["workspace_path"]))

    review = ReviewResult.model_validate_json(workspace.review_json.read_text())
    assert review.findings, "live review returned no findings"
    non_pass = [f for f in review.findings if f.verdict != "PASS"]
    assert non_pass, "live review missed the planted Start Date error"
    assert workspace.review_md.is_file()

    # The policy reached the Reviewer's explicit inputs.
    reviewer_inputs = json.loads(
        (workspace.reviewer_outputs / "inputs.json").read_text()
    )
    assert reviewer_inputs["review_policy"]["strict_fields"] == [
        "Project ID*",
        "Start Date",
    ]

    # The OS-enforced read-only sandbox left the draft untouched.
    before, after = codex.observations["reviewer"]
    assert before == after

    assert workspace.final_xlsx.is_file()

    err = capsys.readouterr().err
    assert "Codex auth: ChatGPT subscription (auth.json)" in err
    assert "Codex API key env vars: cleared (CODEX_API_KEY, CODEX_ACCESS_TOKEN)" in err


def test_live_targeted_rereview_of_rebutted_cells(inputs, tmp_path, monkeypatch):
    # Deterministic re-review trigger: a fake WARN finding on a correct
    # value, rebutted by a fake revision — only the re-review is live.
    fake_review = {
        "findings": [
            {
                "cell": "A2",
                "verdict": "PASS",
                "issue_type": None,
                "current_value": "PRJ-2008",
                "recommended_value": None,
                "evidence": [evidence("began operations on 2008-03-15")],
                "reviewer_comment": "ID matches the constructed format.",
                "missed_data": False,
            },
            {
                "cell": "D2",
                "verdict": "WARN",
                "issue_type": "date_doubt",
                "current_value": "2008-03-15",
                "recommended_value": None,
                "evidence": [evidence("began operations on 2008-03-15")],
                "reviewer_comment": (
                    "The start date may refer to the planning phase rather"
                    " than the delivery launch; confirm against the brief."
                ),
                "missed_data": False,
            },
        ]
    }
    fake_revision = {
        "decisions": [
            {
                "cell": "D2",
                "action": "REBUT",
                "original_value": "2008-03-15",
                "proposed_value": None,
                "note_append": None,
                "evidence": [evidence("began operations on 2008-03-15")],
                "justification": (
                    "The brief states operations began on 2008-03-15; the"
                    " drafted value quotes it verbatim."
                ),
            }
        ]
    }

    plant_invalid_credentials(monkeypatch)
    codex = HashObservingRuntime(CodexRuntime())
    fakes = FakeAgentRuntime({"reviewer": fake_review, "revision": fake_revision})
    state = start_run(
        inputs,
        tmp_path,
        {"reviewer": fakes, "revision": fakes, "re_review": codex},
        filler_fixture(start_date="2008-03-15"),
    )
    workspace = Workspace(Path(state["workspace_path"]))

    result = ReReviewResult.model_validate_json(workspace.re_review_json.read_text())
    # Exactly the rebutted cell, no additions — and a definite verdict.
    assert [verdict.cell for verdict in result.verdicts] == ["D2"]
    assert result.verdicts[0].verdict in {"WITHDRAWN", "UPHELD"}
    assert result.verdicts[0].reviewer_comment.strip()

    # The re-review could not mutate the workbook.
    before, after = codex.observations["re_review"]
    assert before == after

    assert workspace.final_xlsx.is_file()
