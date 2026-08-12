from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import src.gui.main_window_2 as main_window_module
from src.gui.main_window_2 import MainWindow
from src.models.progress.progress_state import ProgressState


class _Runner:
    def __init__(self, active: tuple[str, ...] = (), *, busy: bool = False) -> None:
        self.active_task_ids = active
        self.is_busy = busy

    def is_task_active(self, task_id: str) -> bool:
        return task_id in self.active_task_ids


def _window(*, active: tuple[str, ...] = (), busy: bool = False):
    events: list[object] = []
    return SimpleNamespace(
        task_runner=_Runner(active, busy=busy),
        instance_controller=SimpleNamespace(
            CREATE_TASK_ID="instance.create",
            LOADER_CHANGE_TASK_ID="instance.loader",
            LOADER_REPAIR_TASK_ID="instance.loader.repair",
            FORGE_RESTORE_TASK_ID="instance.loader.restore",
        ),
        launch_controller=SimpleNamespace(TASK_ID="minecraft.launch"),
        _suppress_loader_progress=False,
        _progress_task_id="",
        _progress_task_order=[],
        _progress_task_messages={},
        _progress_revision=0,
        _on_progress=events.append,
    ), events


def test_profileless_task_start_replaces_stale_terminal_progress() -> None:
    window, events = _window()

    MainWindow._on_task_started(window, "versions.load", "Loading Minecraft versions...", False)

    assert window._progress_task_id == "versions.load"
    assert len(events) == 1
    assert events[0].state is ProgressState.RUNNING
    assert events[0].message == "Loading Minecraft versions..."
    assert events[0].percentage is None


def test_older_task_completion_does_not_overwrite_newer_progress(monkeypatch) -> None:
    window, events = _window(active=("storage.legacy.probe",))
    window._progress_task_id = "storage.legacy.probe"
    window._progress_task_order[:] = ["update.check.auto", "storage.legacy.probe"]
    window._progress_task_messages.update({
        "update.check.auto": "Checking for updates...",
        "storage.legacy.probe": "Analyzing legacy launcher storage...",
    })
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda _delay, callback: callback())

    MainWindow._on_task_succeeded(window, "update.check.auto", object())

    assert events == []
    assert window._progress_task_id == "storage.legacy.probe"


def test_current_legacy_probe_completion_reaches_ready_state(monkeypatch) -> None:
    window, events = _window()
    window._progress_task_id = "storage.legacy.probe"
    window._progress_task_order[:] = ["storage.legacy.probe"]
    window._progress_task_messages["storage.legacy.probe"] = "Analyzing legacy launcher storage..."
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda _delay, callback: callback())

    MainWindow._on_task_succeeded(window, "storage.legacy.probe", object())

    assert len(events) == 1
    assert events[0].state is ProgressState.SUCCEEDED
    assert events[0].message == "storage.legacy.scan.completed"
    assert window._progress_task_id == ""


def test_cancelled_replaced_generation_cannot_clear_new_generation(monkeypatch) -> None:
    window, events = _window(active=("java.scan",))
    window._progress_task_id = "java.scan"
    window._progress_task_order[:] = ["java.scan"]
    window._progress_task_messages["java.scan"] = "Scanning Java installations..."
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda _delay, callback: callback())

    MainWindow._on_task_cancelled(window, "java.scan")

    assert events == []
    assert window._progress_task_id == "java.scan"
