from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.runtime.game_window_activator import GameWindowActivator
from src.core.system.platform_info import PlatformInfo


class DummyProcess:
    def __init__(self, pid: int = 12345, running: bool = True) -> None:
        self.pid = pid
        self._running = running

    def poll(self) -> int | None:
        return None if self._running else 0


def test_allow_foreground_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PlatformInfo, "is_windows", lambda: False)
    assert GameWindowActivator.allow_foreground(12345) is False


def test_find_window_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PlatformInfo, "is_windows", lambda: False)
    assert GameWindowActivator.find_window_for_pid(12345) is None


def test_activate_window_non_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PlatformInfo, "is_windows", lambda: False)
    assert GameWindowActivator.activate_window(9999) is False


def test_watch_and_activate_rejects_invalid_pid() -> None:
    proc = DummyProcess(pid=0)
    assert GameWindowActivator.watch_and_activate(proc) is None


def test_watch_and_activate_triggers_callback_when_window_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameWindowActivator, "allow_foreground", lambda pid: True)
    monkeypatch.setattr(GameWindowActivator, "find_window_for_pid", lambda pid: 54321)
    activated = []
    monkeypatch.setattr(GameWindowActivator, "activate_window", lambda hwnd: activated.append(hwnd) or True)

    found = []
    proc = DummyProcess(pid=12345)
    thread = GameWindowActivator.watch_and_activate(
        proc,
        timeout_seconds=2.0,
        poll_interval=0.01,
        on_window_found=found.append,
    )
    assert thread is not None
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert activated == [54321]
    assert found == [54321]


def test_watch_and_activate_stops_when_process_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GameWindowActivator, "allow_foreground", lambda pid: True)
    monkeypatch.setattr(GameWindowActivator, "find_window_for_pid", lambda pid: None)

    proc = DummyProcess(pid=12345, running=True)
    thread = GameWindowActivator.watch_and_activate(
        proc,
        timeout_seconds=5.0,
        poll_interval=0.01,
    )
    assert thread is not None
    # Process exits shortly
    proc._running = False
    thread.join(timeout=2.0)
    assert not thread.is_alive()
