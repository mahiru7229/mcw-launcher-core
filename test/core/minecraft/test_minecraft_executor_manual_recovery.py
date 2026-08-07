from __future__ import annotations

from pathlib import Path

import pytest

from src.core.curseforge.curseforge_errors import CurseForgeManagedFilesRequired
from src.core.minecraft.minecraft_executor import MinecraftExecutor
from src.core.network.download_pause import DownloadCancelledError, download_pause_controller
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.instance.instance import Instance


@pytest.fixture(autouse=True)
def reset_pause_controller():
    download_pause_controller.finish()
    yield
    download_pause_controller.finish()


def _instance(tmp_path: Path) -> Instance:
    root = tmp_path / "instance"
    root.mkdir()
    return Instance(instance_id="id", name="Manual Pack", version_id="1.12.2", instance_dir=root, mod_loader=("forge", "14.23.5.2860"))


def _error(instance: Instance) -> CurseForgeManagedFilesRequired:
    requirement = CurseForgeManualDownload(
        project_id=1,
        file_id=2,
        project_name="Restricted Mod",
        file_name="restricted.jar",
        file_size=10,
        sha1="a" * 40,
        project_url="https://example.invalid/project",
        reason="Manual download required",
    )
    return CurseForgeManagedFilesRequired(instance, (requirement,), "manual file required")


def test_manual_content_pause_retries_only_the_blocked_provider_stage(tmp_path):
    instance = _instance(tmp_path)
    calls = []
    required = _error(instance)

    def ensure():
        calls.append("ensure")
        if len(calls) == 1:
            raise required
        return ("ready",)

    seen = []

    def on_required(error):
        seen.append(error)
        assert download_pause_controller.is_paused is True
        assert error.launch_lock_token == "owned-token"
        assert download_pause_controller.request_resume() is True

    download_pause_controller.begin()
    result = MinecraftExecutor._run_with_manual_content_pause(ensure, (CurseForgeManagedFilesRequired,), on_required, "owned-token")

    assert result == ("ready",)
    assert calls == ["ensure", "ensure"]
    assert seen == [required]
    assert download_pause_controller.is_paused is False


def test_manual_content_without_callback_preserves_existing_error_behavior(tmp_path):
    instance = _instance(tmp_path)
    required = _error(instance)

    with pytest.raises(CurseForgeManagedFilesRequired):
        MinecraftExecutor._run_with_manual_content_pause(lambda: (_ for _ in ()).throw(required), (CurseForgeManagedFilesRequired,), None)


def test_cancelling_while_waiting_for_manual_content_stops_launch(tmp_path):
    instance = _instance(tmp_path)
    required = _error(instance)

    def on_required(_error):
        assert download_pause_controller.request_cancel() is True

    download_pause_controller.begin()
    with pytest.raises(DownloadCancelledError):
        MinecraftExecutor._run_with_manual_content_pause(lambda: (_ for _ in ()).throw(required), (CurseForgeManagedFilesRequired,), on_required)
