"""Fake agent runtime (plan section 32): replays fixture JSON per role."""

from workflow_app.runtimes.base import AgentResult


class FakeAgentRuntime:
    name = "fake"

    def __init__(self, outputs):
        # outputs: role name -> a structured fixture output, or a list of
        # them replayed one per call. A list matters for the scoping role,
        # which the graph invokes once per round: a single fixture would
        # repeat its questions and pause the run again every round.
        self._outputs = {
            role: list(_as_sequence(output)) for role, output in outputs.items()
        }

    def run(self, request):
        if request.role not in self._outputs:
            raise KeyError(
                f"FakeAgentRuntime has no fixture output for role {request.role!r}"
            )
        steps = self._outputs[request.role]
        # The last step repeats, so a single fixture behaves as before.
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        return AgentResult(status="ok", output=step)


def _as_sequence(output):
    return output if isinstance(output, list) else [output]
