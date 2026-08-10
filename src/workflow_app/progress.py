"""Stage-level CLI output and structured workflow progress events."""

import sys
from datetime import UTC, datetime


def _event(event_type, **payload):
    return {
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        **payload,
    }


def emit(message, callback=None):
    print(f"[workflow] {message}", file=sys.stderr)
    if callback is not None:
        callback(_event("progress", message=message))


class ProgressReporter:
    """Own the engine event contract while preserving plain CLI output."""

    def __init__(self, callback=None):
        self.callback = callback
        self.phase = "INITIALIZING"

    def emit(self, message):
        phase = self.phase

        def forward(event):
            self.callback({**event, "phase": phase})

        emit(message, forward if self.callback is not None else None)

    def phase_change(self, phase, status):
        self.phase = phase
        self._send("phase_change", phase=phase, status=status)

    def paused(self, reason, questions_artifact):
        self._send(
            "paused",
            reason=reason,
            questions_artifact=str(questions_artifact),
        )

    def completed(self, final_xlsx):
        self._send("completed", final_xlsx=str(final_xlsx))

    def failed(self, error):
        self._send("failed", error=str(error))

    def cancelled(self):
        self._send("failed", error="Run cancelled", reason="cancelled")

    def _send(self, event_type, **payload):
        if self.callback is not None:
            self.callback(_event(event_type, **payload))
