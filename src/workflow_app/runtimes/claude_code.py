"""Claude Code runtime adapter (plan sections 10, 13, 31).

Launches the claude CLI non-interactively in structured-output mode
(`claude --print --output-format json --json-schema ...`), scoped to the
run workspace. The adapter owns process launch, auth environment,
structured-output capture, and failure mapping only: a process that ran
and failed returns an error AgentResult (classified by the engine as
runtime_process_failure); an inability to invoke raises (classified as
invocation_failure). Retry and degrade policy live in the engine.
"""

import json
import os
from pathlib import Path

from workflow_app.cancellation import run_process
from workflow_app.models.extraction import ExtractionResult
from workflow_app.models.revision import RevisionResult
from workflow_app.models.scoping import ScopingQuestions
from workflow_app.progress import emit
from workflow_app.runtimes.base import AgentResult

# Subscription-first auth (plan section 10): API-billing credentials are
# cleared from the child environment so the CLI uses its normal OAuth /
# keychain login and never silently falls back to API billing.
API_KEY_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Role key -> (prompt file, structured-output contract). Role keys name
# invocation kinds (ADR 0014); every Claude role maps to this one runtime.
ROLES = {
    "scoping": ("scoping.md", ScopingQuestions),
    "filler": ("filler.md", ExtractionResult),
    "revision": ("revision.md", RevisionResult),
}

# Tail lengths keep stderr/stdout excerpts in error strings bounded.
_ERROR_EXCERPT = 500


def child_env():
    env = {k: v for k, v in os.environ.items() if k not in API_KEY_ENV_VARS}
    # The agent's instructions come exclusively from the version-controlled
    # prompt files (plan section 39); personal CLAUDE.md memory files must
    # not leak into the invocation (ADR 0017).
    env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    return env


def print_auth_diagnostic():
    # Startup diagnostic (plan section 10). The subscription-vs-API
    # distinction cannot be reliably verified at the CLI level, so the
    # application warns and proceeds instead of failing.
    emit("Claude Code auth: OAuth (subscription - best effort)")
    present = [name for name in API_KEY_ENV_VARS if os.environ.get(name)]
    detail = f"cleared ({', '.join(present)})" if present else "none set"
    emit(f"API key env vars: {detail}")
    emit(
        "Warning: Claude Code subscription auth cannot be verified at the "
        "CLI level; proceeding (best effort)."
    )


class ClaudeCodeRuntime:
    name = "claude-code"

    def __init__(self, command="claude", model=None):
        # model: full model name (a "[1m]" suffix selects the 1M-context
        # variant); None uses the CLI's own default.
        self._command = command
        self._model = model
        print_auth_diagnostic()

    def run(self, request):
        # An unknown role raises (KeyError): the invocation itself is
        # impossible, which is the engine's invocation_failure class.
        prompt_file, contract = ROLES[request.role]
        prompt = (PROMPTS_DIR / prompt_file).read_text()
        schema = json.dumps(contract.model_json_schema())

        argv = [
            self._command,
            "--print",
            "--output-format",
            "json",
            "--json-schema",
            schema,
            # Headless runs cannot answer permission prompts. Tool
            # access is deliberately unrestricted; READ/WRITE
            # boundaries are prompt-instructed (plan section 13).
            "--permission-mode",
            "bypassPermissions",
        ]
        if self._model is not None:
            argv += ["--model", self._model]

        process = run_process(
            argv,
            input=prompt,
            cwd=request.workspace_path,
            env=child_env(),
            cancellation=request.cancellation,
        )
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip()
            return AgentResult(
                status="error",
                error=(
                    f"claude exited with code {process.returncode}: "
                    f"{detail[-_ERROR_EXCERPT:]}"
                ),
            )

        try:
            envelope = json.loads(process.stdout)
        except json.JSONDecodeError:
            return AgentResult(
                status="error",
                error=(
                    "claude produced non-JSON stdout: "
                    f"{process.stdout[-_ERROR_EXCERPT:]!r}"
                ),
            )

        self._record_envelope(request, envelope)
        if envelope.get("is_error"):
            return AgentResult(
                status="error",
                error=(
                    f"claude reported an error ({envelope.get('subtype')}): "
                    f"{str(envelope.get('result'))[-_ERROR_EXCERPT:]}"
                ),
            )
        structured = envelope.get("structured_output")
        if structured is None:
            return AgentResult(
                status="error",
                error=(
                    "claude returned no structured output "
                    f"(subtype: {envelope.get('subtype')})"
                ),
            )
        return AgentResult(status="ok", output=structured)

    def _record_envelope(self, request, envelope):
        # The full result envelope (usage, cost, duration, session id) is
        # operational metadata worth keeping (plan section 38); the last
        # attempt per role wins, matching the engine's raw-output rule.
        # The workspace layout guarantees logs/ exists; a broken workspace
        # raises here rather than silently dropping the record.
        path = (
            Path(request.workspace_path) / "logs" / f"claude_{request.role}_result.json"
        )
        path.write_text(json.dumps(envelope, indent=2))
