"""Codex runtime adapter (plan sections 10, 13, 23, 31).

Launches the codex CLI non-interactively in structured-output mode
(`codex exec --sandbox read-only --output-schema ...`), scoped to the
run workspace. The read-only sandbox is OS-enforced: the Reviewer
physically cannot mutate the workbook. The adapter owns process launch,
auth environment, structured-output capture, and failure mapping only:
a process that ran and failed returns an error AgentResult (classified
by the engine as runtime_process_failure); an inability to invoke
raises (invocation_failure). Retry and degrade policy live in the
engine.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

from workflow_app.models.review import ReReviewResult, ReviewResult
from workflow_app.progress import emit
from workflow_app.runtimes.base import AgentResult

# Subscription auth is runtime-enforced through auth.json (plan
# section 10): with these env credentials cleared, the CLI can only
# authenticate via `codex login` and never falls back to API billing.
API_KEY_ENV_VARS = ("CODEX_API_KEY", "CODEX_ACCESS_TOKEN")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Role key -> (prompt file, structured-output contract). Role keys name
# invocation kinds (ADR 0014); both Codex roles map to this one runtime.
ROLES = {
    "reviewer": ("reviewer.md", ReviewResult),
    "re_review": ("re_review.md", ReReviewResult),
}

_ERROR_EXCERPT = 500

# Wire representation of a contract `Any` cell value: workbook cell
# values are scalars (dates travel as strings).
_CELL_VALUE_TYPES = {"type": ["string", "number", "boolean", "null"]}


def strict_schema(node):
    # OpenAI structured outputs demand a stricter dialect than pydantic
    # emits: every object must list all of its properties as required
    # (optionality is expressed by a null type union, which pydantic
    # already produces), and every schema needs a type — a contract
    # `Any` (no constraint) becomes the concrete cell-value union.
    if isinstance(node, dict):
        if not node:
            return dict(_CELL_VALUE_TYPES)
        transformed = {key: strict_schema(value) for key, value in node.items()}
        if transformed.get("type") == "object" and "properties" in transformed:
            transformed["required"] = sorted(transformed["properties"])
        return transformed
    if isinstance(node, list):
        return [strict_schema(value) for value in node]
    return node


def child_env():
    return {k: v for k, v in os.environ.items() if k not in API_KEY_ENV_VARS}


def codex_home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def print_auth_diagnostic():
    # Startup diagnostic (plan section 10). Unlike Claude Code, the
    # Codex auth mode is verifiable: auth.json records it. Anything
    # other than a chatgpt-mode auth.json warns and proceeds.
    auth_file = codex_home() / "auth.json"
    mode = None
    if auth_file.is_file():
        try:
            mode = json.loads(auth_file.read_text()).get("auth_mode")
        except (OSError, json.JSONDecodeError):
            mode = None
    if mode == "chatgpt":
        emit("Codex auth: ChatGPT subscription (auth.json)")
    else:
        detail = f"auth_mode: {mode}" if auth_file.is_file() else "auth.json missing"
        emit(f"Codex auth: unverified ({detail})")
        emit(
            "Warning: Codex subscription auth could not be verified;"
            " proceeding (best effort)."
        )
    present = [name for name in API_KEY_ENV_VARS if os.environ.get(name)]
    detail = f"cleared ({', '.join(present)})" if present else "none set"
    emit(f"Codex API key env vars: {detail}")


class CodexRuntime:
    name = "codex"

    def __init__(self, command="codex", model=None, effort=None):
        # model: codex model name; effort: model_reasoning_effort value
        # (none/minimal/low/medium/high/xhigh/max/ultra). None leaves
        # the CLI's own default in place. --ignore-user-config skips
        # ~/.codex/config.toml, so these are the only way an engine
        # invocation picks a model or effort deliberately.
        self._command = command
        self._model = model
        self._effort = effort
        print_auth_diagnostic()

    def run(self, request):
        # An unknown role raises (KeyError): the invocation itself is
        # impossible, which is the engine's invocation_failure class.
        prompt_file, contract = ROLES[request.role]
        prompt = (PROMPTS_DIR / prompt_file).read_text()

        # --output-schema takes a file; the final message lands in a
        # file as well. Both live outside the workspace so the run
        # leaves no unaudited scratch files in it.
        with tempfile.TemporaryDirectory(prefix="codex-invoke-") as scratch:
            schema_file = Path(scratch) / "output_schema.json"
            schema_file.write_text(
                json.dumps(strict_schema(contract.model_json_schema()))
            )
            message_file = Path(scratch) / "last_message.json"

            argv = [
                self._command,
                "exec",
                # OS-enforced read-only sandbox (plan sections 13, 23).
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_file),
                "--output-last-message",
                str(message_file),
                # Run workspaces are not git repositories.
                "--skip-git-repo-check",
                # No session persistence outside the workspace.
                "--ephemeral",
                # The agent's instructions come exclusively from the
                # version-controlled prompt files (ADR 0017); auth
                # still resolves through CODEX_HOME.
                "--ignore-user-config",
            ]
            if self._model is not None:
                argv += ["--model", self._model]
            if self._effort is not None:
                argv += ["-c", f'model_reasoning_effort="{self._effort}"']

            process = subprocess.run(
                argv,
                input=prompt,
                cwd=request.workspace_path,
                env=child_env(),
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode != 0:
                detail = process.stderr.strip() or process.stdout.strip()
                return AgentResult(
                    status="error",
                    error=(
                        f"codex exited with code {process.returncode}: "
                        f"{detail[-_ERROR_EXCERPT:]}"
                    ),
                )
            if not message_file.is_file():
                return AgentResult(
                    status="error",
                    error="codex wrote no final message file",
                )
            raw = message_file.read_text()

        try:
            output = json.loads(raw)
        except json.JSONDecodeError:
            return AgentResult(
                status="error",
                error=f"codex final message is not JSON: {raw[-_ERROR_EXCERPT:]!r}",
            )
        return AgentResult(status="ok", output=output)
