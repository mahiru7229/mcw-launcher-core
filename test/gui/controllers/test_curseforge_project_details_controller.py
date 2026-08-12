import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.controllers.curseforge_controller import CurseForgeController
from src.gui.task_runner import TaskCancellationToken, TaskRunner


def test_controller_loads_project_details_through_core_client(gui_app, monkeypatch):
    task_runner = TaskRunner()
    controller = CurseForgeController(task_runner)
    calls = []
    project = object()
    monkeypatch.setattr(task_runner, "run", lambda task_id, task, message, blocking=False, **_kwargs: calls.append((task_id, task(TaskCancellationToken()), message, blocking)) or True)

    from src.core.curseforge.curseforge_client import CurseForgeClient
    monkeypatch.setattr(CurseForgeClient, "get_project_details", lambda project_id: project)

    assert controller.load_project_details("mod", 42, "neoforge") is True
    assert calls[0][0] == "curseforge.details.mod.42.neoforge"
    assert calls[0][1] == ("mod", 42, "neoforge", project)


def test_controller_emits_project_details(gui_app):
    controller = CurseForgeController(TaskRunner())
    emitted = []
    project = object()
    controller.project_details_changed.connect(lambda *args: emitted.append(args))

    controller._on_task_succeeded("curseforge.details.mod.42.fabric", ("mod", 42, "fabric", project))

    assert emitted == [("mod", 42, "fabric", project)]
