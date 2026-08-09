"""Fake agent runtime (plan section 32): replays fixture JSON per role."""

from workflow_app.runtimes.base import AgentResult


class FakeAgentRuntime:
    name = "fake"

    def __init__(self, outputs):
        # outputs: role name -> structured fixture output (dict)
        self._outputs = dict(outputs)

    def run(self, request):
        if request.role not in self._outputs:
            raise KeyError(
                f"FakeAgentRuntime has no fixture output for role {request.role!r}"
            )
        return AgentResult(status="ok", output=self._outputs[request.role])
