import sys
import threading
import time

from workflow_app.cancellation import (
    CancellationToken,
    WorkflowCancelled,
    run_process,
)


def test_cancellation_terminates_and_reaps_a_registered_subprocess(tmp_path):
    marker = tmp_path / "started"
    cancellation = CancellationToken()
    outcome = []

    def invoke():
        try:
            run_process(
                [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; import time;"
                        f" Path({str(marker)!r}).write_text('started');"
                        " time.sleep(60)"
                    ),
                ],
                input="",
                cwd=tmp_path,
                env=None,
                cancellation=cancellation,
            )
        except WorkflowCancelled as exc:
            outcome.append(exc)

    worker = threading.Thread(target=invoke)
    worker.start()
    for _ in range(100):
        if marker.is_file():
            break
        time.sleep(0.01)
    assert marker.is_file()

    cancellation.cancel()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], WorkflowCancelled)
