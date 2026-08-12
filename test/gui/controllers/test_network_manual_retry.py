from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Signal

from src.gui.controllers.base_controller import BaseController
from src.gui.task_runner import TaskCancellationToken


class _Runner(QObject):
    task_succeeded = Signal(str, object)
    task_failed = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, object, str, bool]] = []
        self.active = False

    def run(self, task_id, task, message, blocking=False, **_kwargs):
        self.calls.append((task_id, task, message, blocking))
        return True

    def is_task_active(self, _task_id: str) -> bool:
        return self.active


def test_retryable_failure_offers_and_restarts_same_network_task(gui_app) -> None:
    controller = BaseController()
    runner = _Runner()
    offered: list[tuple[str, str, str]] = []
    controller.network_retry_available.connect(lambda *args: offered.append(args))

    controller._run_network_task(runner, "metadata.load", lambda: "ok", "Loading metadata", blocking=False)

    assert controller._offer_network_retry("metadata.load", "Metadata", TimeoutError("request timed out")) is True
    assert offered == [("metadata.load", "Metadata", "request timed out")]
    assert controller.retry_network_task("metadata.load") is True
    assert len(runner.calls) == 2
    assert runner.calls[-1][0] == "metadata.load"
    assert runner.calls[-1][2:] == ("Loading metadata", False)
    assert runner.calls[-1][1](TaskCancellationToken()) == "ok"


def test_permanent_failure_does_not_offer_manual_retry(gui_app) -> None:
    controller = BaseController()
    runner = _Runner()
    offered: list[tuple[str, str, str]] = []
    controller.network_retry_available.connect(lambda *args: offered.append(args))
    controller._run_network_task(runner, "metadata.load", lambda: None, "Loading metadata", blocking=False)

    assert controller._offer_network_retry("metadata.load", "Metadata", RuntimeError("404 Not Found")) is False
    assert offered == []


def test_manual_retry_refuses_duplicate_active_task(gui_app) -> None:
    controller = BaseController()
    runner = _Runner()
    controller._run_network_task(runner, "metadata.load", lambda: None, "Loading metadata", blocking=False)
    runner.active = True

    assert controller.retry_network_task("metadata.load") is False
    assert len(runner.calls) == 1
