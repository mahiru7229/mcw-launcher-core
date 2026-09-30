from __future__ import annotations

import sys
from pathlib import Path

from src.gui import app_restart


def test_frozen_restart_marks_replacement_as_independent_pyinstaller_instance(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    environment = app_restart.restart_environment({"EXAMPLE": "value"})

    assert environment["EXAMPLE"] == "value"
    assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"


def test_source_restart_does_not_keep_pyinstaller_reset_marker(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)

    environment = app_restart.restart_environment({"PYINSTALLER_RESET_ENVIRONMENT": "1"})

    assert "PYINSTALLER_RESET_ENVIRONMENT" not in environment


def test_frozen_restart_spawns_the_current_executable_with_reset_environment(monkeypatch, tmp_path: Path) -> None:
    executable_path = tmp_path / "MCW Launcher.exe"
    calls: list[tuple[list[str], dict[str, object]]] = []

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable_path))
    monkeypatch.setattr(sys, "argv", [str(executable_path), "--example"])

    def fake_popen(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(app_restart.subprocess, "Popen", fake_popen)

    assert app_restart.start_restarted_process()
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == [str(executable_path.resolve()), "--example"]
    assert Path(str(kwargs["cwd"])) == executable_path.resolve().parent
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert environment["PYINSTALLER_RESET_ENVIRONMENT"] == "1"
