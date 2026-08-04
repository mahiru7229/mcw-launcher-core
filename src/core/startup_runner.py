from __future__ import annotations

from collections.abc import Callable
from queue import Empty, Queue
from threading import Thread
from time import monotonic
from typing import Any
import traceback

StartupTask = Callable[[Callable[[int, str], None]], Any]
StartupProgressHandler = Callable[[int, str], None]
EventPump = Callable[[], None]


class StartupTimeoutError(RuntimeError):
    def __init__(self, stage_key: str, timeout_seconds: float) -> None:
        self.stage_key = str(stage_key or "startup.starting")
        self.timeout_seconds = float(timeout_seconds)
        super().__init__(f"Startup timed out after {self.timeout_seconds:g} seconds during '{self.stage_key}'.")


class StartupWorkerError(RuntimeError):
    def __init__(self, error: BaseException, traceback_text: str) -> None:
        self.original_error = error
        self.traceback_text = str(traceback_text)
        super().__init__(f"{type(error).__name__}: {error}")


def run_startup_task(task: StartupTask, on_progress: StartupProgressHandler, pump_events: EventPump, timeout_seconds: float = 45.0) -> Any:
    """Run blocking startup I/O away from the Qt thread while keeping the splash responsive."""
    events: Queue[tuple[str, object, object]] = Queue()
    last_stage = "startup.starting"
    deadline = monotonic() + max(0.1, float(timeout_seconds))

    def report(percent: int, message_key: str) -> None:
        events.put(("progress", int(percent), str(message_key)))

    def worker() -> None:
        try:
            result = task(report)
        except BaseException as error:
            events.put(("error", error, traceback.format_exc()))
        else:
            events.put(("success", result, None))

    Thread(target=worker, name="mcw-startup-bootstrap", daemon=True).start()

    while True:
        try:
            event_type, value, extra = events.get(timeout=0.02)
        except Empty:
            pump_events()
            if monotonic() >= deadline:
                raise StartupTimeoutError(last_stage, timeout_seconds)
            continue

        if event_type == "progress":
            last_stage = str(extra)
            on_progress(int(value), last_stage)
            pump_events()
            continue
        if event_type == "error":
            raise StartupWorkerError(value, str(extra)) from None
        if event_type == "success":
            return value
        raise RuntimeError(f"Unknown startup event: {event_type}")
