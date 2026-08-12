from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import src.gui.main_window_2 as main_window_module
from src.gui.main_window_2 import MainWindow
from src.models.progress.progress_event import ProgressEvent
from src.models.progress.progress_stage import ProgressStage


class _LaunchControl:
    def __init__(self) -> None:
        self.completed_messages: list[tuple[str, str]] = []
        self.failed_messages: list[tuple[str, str | None]] = []
        self.progress_events: list[object] = []

    def set_operation_completed(self, status: str, detail: str) -> None:
        self.completed_messages.append((status, detail))

    def set_failed(self, status: str, detail: str | None = None) -> None:
        self.failed_messages.append((status, detail))

    def set_progress_event(self, event: object) -> None:
        self.progress_events.append(event)


class _StatusTarget:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def set_status(self, message: str) -> None:
        self.messages.append(message)


def _window_stub() -> SimpleNamespace:
    return SimpleNamespace(
        task_runner=SimpleNamespace(
            is_shutting_down=False,
            is_task_active=lambda _task_id: False,
        ),
        _closing=False,
        instance_controller=SimpleNamespace(
            CREATE_TASK_ID="instance.create",
            REPAIR_TASK_ID="instance.repair.full",
            LOADER_CHANGE_TASK_ID="instance.loader",
            LOADER_REPAIR_TASK_ID="instance.loader.repair",
            FORGE_RESTORE_TASK_ID="instance.loader.restore",
        ),
        launch_controller=SimpleNamespace(TASK_ID="minecraft.launch"),
        launch_control=_LaunchControl(),
        home_page=_StatusTarget(),
        right_panel=_StatusTarget(),
        mod_manager_dialog=SimpleNamespace(set_update_error=lambda _message: None),
        _suppress_loader_progress=False,
    )


def test_successful_forge_repair_publishes_terminal_ready_state(monkeypatch):
    window = _window_stub()
    scheduled = []
    monkeypatch.setattr(main_window_module.QTimer, "singleShot", lambda delay, callback: scheduled.append((delay, callback)))

    MainWindow._on_task_succeeded(window, "instance.loader.repair", object())

    assert window._suppress_loader_progress is True
    assert len(scheduled) == 1
    assert scheduled[0][0] == 0
    scheduled[0][1]()
    assert window.launch_control.completed_messages == [
        ("loader.progress.repaired", "loader.progress.repaired_detail")
    ]


def test_late_loader_progress_cannot_overwrite_terminal_state():
    window = _window_stub()
    window._suppress_loader_progress = True
    event = ProgressEvent(
        stage=ProgressStage.INSTALLING_MOD_LOADER,
        message="Still installing...",
    )

    MainWindow._on_progress(window, event)

    assert window.launch_control.progress_events == []
    assert window.home_page.messages == []
    assert window.right_panel.messages == []


def test_failed_forge_repair_leaves_terminal_failed_progress_state():
    window = _window_stub()

    MainWindow._on_task_failed(window, "instance.loader.repair", RuntimeError("repair failed"))

    assert window._suppress_loader_progress is True
    assert window.launch_control.failed_messages == [
        ("Mod loader operation failed", "Open Logs to see the full error details.")
    ]
    assert window.home_page.messages
    assert window.right_panel.messages
