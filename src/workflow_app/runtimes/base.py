"""Agent runtime adapter interface (plan section 31).

Runtime adapters launch an agent process, capture its structured result
and status, and map failures. They contain no business workflow logic.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentRequest:
    role: str
    workspace_path: str
    prompt: str = ""


@dataclass(frozen=True)
class AgentResult:
    status: str  # "ok" | "error"
    output: dict | None = None
    error: str | None = None


class AgentRuntime(Protocol):
    def run(self, request: AgentRequest) -> AgentResult: ...
