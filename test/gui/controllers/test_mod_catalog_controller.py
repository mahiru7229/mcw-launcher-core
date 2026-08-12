import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.controllers.mod_catalog_controller import ModCatalogController
from src.gui.task_runner import TaskCancellationToken, TaskRunner


def test_catalog_search_is_not_filtered_to_a_single_minecraft_version(gui_app, monkeypatch):
    runner = TaskRunner()
    controller = ModCatalogController(runner)
    captured = []
    monkeypatch.setattr(runner, "run", lambda task_id, task, message, blocking=False, **_kwargs: captured.append((task_id, task(TaskCancellationToken()), blocking)))

    from src.core.modrinth.modrinth_client import ModrinthClient
    monkeypatch.setattr(ModrinthClient, "search_projects", lambda **kwargs: kwargs)

    controller.search("sodium", "downloads", 0, "fabric")

    task_id, result, blocking = captured[0]
    assert task_id == "mod_catalog.search.fabric"
    assert result[0] == "fabric"
    assert result[1]["project_type"] == "mod"
    assert result[1].get("game_version", "") == ""
    assert blocking is False


def test_catalog_emits_results_with_loader(gui_app):
    controller = ModCatalogController(TaskRunner())
    emitted = []
    result = object()
    controller.search_results_changed.connect(lambda *args: emitted.append(args))

    controller._on_task_succeeded("mod_catalog.search.forge", ("forge", result))

    assert emitted == [("forge", result)]
