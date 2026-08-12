from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import src.gui.main_window_2 as main_window_module
from src.gui.main_window_2 import MainWindow


class _ModrinthController:
    def __init__(self, started: bool = True) -> None:
        self.started = started
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    def install_mod(self, instance_name: str, version_id: str, allowed_version_types: tuple[str, ...]) -> bool:
        self.calls.append((instance_name, version_id, tuple(allowed_version_types)))
        return self.started


class _Logs:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def append(self, message: str) -> None:
        self.messages.append(message)


class _ModController:
    def __init__(self) -> None:
        self.calls: list[tuple[object, bool]] = []

    def set_instance(self, instance: object, *, refresh: bool = True) -> None:
        self.calls.append((instance, refresh))


def _window_stub(started: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        instance_controller=SimpleNamespace(CREATE_TASK_ID="instance.create"),
        _pending_prepared_update=None,
        _pending_mod_install_after_create={
            "instance_name": "Fabric Mods",
            "version_id": "mod-version",
            "loader": "fabric",
            "allowed_version_types": ("release", "beta"),
        },
        modrinth_controller=_ModrinthController(started),
        mod_controller=_ModController(),
        logs_page=_Logs(),
        errors=[],
        _on_task_completed=lambda task_id, result: None,
        _show_error=lambda title, message: None,
    )


def test_mod_install_starts_only_after_instance_task_is_settled(monkeypatch) -> None:
    window = _window_stub()
    monkeypatch.setattr(
        main_window_module.InstanceManager,
        "load",
        lambda _name: SimpleNamespace(mod_loader=("fabric", "0.16.14")),
    )

    MainWindow._on_task_settled(window, "instance.create", True, SimpleNamespace(name="Fabric Mods"))

    assert window._pending_mod_install_after_create is None
    assert window.modrinth_controller.calls == [
        ("Fabric Mods", "mod-version", ("release", "beta"))
    ]
    assert len(window.mod_controller.calls) == 1
    selected_instance, refresh = window.mod_controller.calls[0]
    assert selected_instance.mod_loader == ("fabric", "0.16.14")
    assert refresh is False


def test_failed_instance_creation_clears_pending_mod_install() -> None:
    window = _window_stub()

    MainWindow._on_task_settled(window, "instance.create", False, RuntimeError("failed"))

    assert window._pending_mod_install_after_create is None
    assert window.modrinth_controller.calls == []
    assert window.logs_page.messages
