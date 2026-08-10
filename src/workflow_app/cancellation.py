"""Cooperative cancellation shared by the server, engine, and runtimes."""

import os
import signal
import subprocess
import threading


class WorkflowCancelled(BaseException):
    """The operator cancelled an owned workflow execution."""


class CancellationToken:
    def __init__(self):
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._processes = set()

    def cancel(self):
        self._cancelled.set()
        with self._lock:
            processes = tuple(self._processes)
        for process in processes:
            _kill_process_tree(process)

    def wait(self, timeout=None):
        return self._cancelled.wait(timeout)

    def raise_if_cancelled(self):
        if self._cancelled.is_set():
            raise WorkflowCancelled("cancelled")

    def register_process(self, process):
        with self._lock:
            self._processes.add(process)
            cancelled = self._cancelled.is_set()
        if cancelled:
            _kill_process_tree(process)

    def unregister_process(self, process):
        with self._lock:
            self._processes.discard(process)


def run_process(argv, *, input, cwd, env, cancellation=None):
    """Run and reap one owned child process, making it cancellable as a group."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
        text=True,
        start_new_session=os.name == "posix",
    )
    if cancellation is not None:
        cancellation.register_process(process)
    try:
        stdout, stderr = process.communicate(input=input)
    finally:
        if cancellation is not None:
            cancellation.unregister_process(process)
    if cancellation is not None:
        cancellation.raise_if_cancelled()
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _kill_process_tree(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass
