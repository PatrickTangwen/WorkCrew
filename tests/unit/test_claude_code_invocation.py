"""Unit tests for the Claude Code adapter's process invocation (ADR 0017).

The adapter's argv encodes policy decisions that nothing else enforces:
the permission mode a headless run may use, structured-output mode, and
the run workspace as the working directory. These assert the launch
itself, with the process call stubbed out.
"""

import json
import subprocess

import pytest

from workflow_app.models.extraction import ExtractionResult
from workflow_app.runtimes import claude_code
from workflow_app.runtimes.base import AgentRequest


@pytest.fixture
def launch(monkeypatch):
    """Capture the argv and kwargs of the adapter's one process launch."""
    calls = []

    def fake_run_process(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        payload = {
            "structured_output": ExtractionResult(
                proposals=[], merges=[]
            ).model_dump()
        }
        return subprocess.CompletedProcess(
            argv, 0, stdout=json.dumps(payload), stderr=""
        )

    monkeypatch.setattr(claude_code, "run_process", fake_run_process)
    monkeypatch.setattr(claude_code, "print_auth_diagnostic", lambda: None)
    return calls


def test_headless_runs_use_the_non_blocking_auto_permission_mode(launch, tmp_path):
    # The adapter records its result envelope under the workspace.
    (tmp_path / "logs").mkdir()
    claude_code.ClaudeCodeRuntime().run(
        AgentRequest(role="filler", workspace_path=str(tmp_path))
    )

    argv = launch[0]["argv"]
    # A mode that can prompt would hang a --print run; bypassPermissions
    # would switch the CLI's own guardrails off entirely (ADR 0017).
    assert argv[argv.index("--permission-mode") + 1] == "auto"
    assert "bypassPermissions" not in argv


def test_invocation_is_structured_output_scoped_to_the_run_workspace(launch, tmp_path):
    # The adapter records its result envelope under the workspace.
    (tmp_path / "logs").mkdir()
    claude_code.ClaudeCodeRuntime().run(
        AgentRequest(role="filler", workspace_path=str(tmp_path))
    )

    call = launch[0]
    assert call["argv"][:1] == ["claude"]
    assert "--print" in call["argv"]
    assert call["argv"][call["argv"].index("--output-format") + 1] == "json"
    schema = json.loads(call["argv"][call["argv"].index("--json-schema") + 1])
    assert schema == ExtractionResult.model_json_schema()
    assert call["cwd"] == str(tmp_path)
    # Personal memory files must not leak into the invocation (ADR 0017).
    assert call["env"]["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
