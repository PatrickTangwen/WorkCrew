"""Agent runtime adapter interface (plan section 31).

Runtime adapters launch an agent process, capture its structured result
and status, and map failures. They contain no business workflow logic.
"""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class AgentRequest:
    role: str
    workspace_path: str
    cancellation: object | None = None


@dataclass(frozen=True)
class AgentResult:
    status: Literal["ok", "error"]
    output: dict | None = None
    error: str | None = None


class AgentRuntime(Protocol):
    # Short runtime identifier recorded in provenance (plan section 19),
    # e.g. "claude-code", "codex", "fake".
    name: str

    def run(self, request: AgentRequest) -> AgentResult: ...
