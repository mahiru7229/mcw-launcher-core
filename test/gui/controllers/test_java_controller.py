from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from src.core.java.java_provisioner import JavaProvisioner
from src.core.network.download_pause import download_pause_controller
from src.gui.controllers.java_controller import JavaController
from src.gui.task_runner import TaskRunner


def test_install_runs_managed_java_task(gui_app, monkeypatch: pytest.MonkeyPatch):
    runner = TaskRunner()
    controller = JavaController(runner)
    installed = Path("runtimes/java-21/bin/javaw.exe")
    calls = []

    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: calls.append((major, force)) or installed)

    captured = {}

    def run(task_id, task, message, blocking=True, **_kwargs):
        captured.update(task_id=task_id, message=message, blocking=blocking, result=task())
        return True

    monkeypatch.setattr(runner, "run", run)

    controller.install(21)

    assert captured["task_id"] == "java.install.21"
    assert captured["blocking"] is True
    assert captured["result"] == installed
    assert calls == [(21, True)]
    assert download_pause_controller.is_active is False


def test_install_accepts_latest_java_feature_release(gui_app, monkeypatch: pytest.MonkeyPatch):
    runner = TaskRunner()
    controller = JavaController(runner)
    installed = Path("runtimes/java-26/bin/javaw.exe")
    calls = []

    monkeypatch.setattr(JavaProvisioner, "install_managed", lambda major, reporter=None, force=False: calls.append((major, force)) or installed)

    captured = {}

    def run(task_id, task, message, blocking=True, **_kwargs):
        captured.update(task_id=task_id, blocking=blocking, result=task())
        return True

    monkeypatch.setattr(runner, "run", run)

    controller.install(26)

    assert captured["task_id"] == "java.install.26"
    assert captured["result"] == installed
    assert calls == [(26, True)]


def test_scan_requests_java_diagnostics_and_latest_release(gui_app, monkeypatch: pytest.MonkeyPatch):
    runner = TaskRunner()
    controller = JavaController(runner)
    task_ids = []

    def run(task_id, task, message, blocking=True, **_kwargs):
        task_ids.append((task_id, blocking))
        return True

    monkeypatch.setattr(runner, "run", run)

    controller.scan()

    assert task_ids == [("java.scan", False), ("java.latest_release", False)]
