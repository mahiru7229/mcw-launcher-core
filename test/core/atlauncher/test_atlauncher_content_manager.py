from __future__ import annotations

from hashlib import md5
from pathlib import Path
import zipfile

import pytest

from src.core.atlauncher.atlauncher_content_manager import ATLauncherContentManager
from src.core.atlauncher.atlauncher_pack_registry import ATLauncherPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.network.download_manager import download_manager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_unit import ProgressUnit


def test_ensure_downloads_deferred_files_with_aggregate_progress(tmp_path, monkeypatch) -> None:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance("id", "ATLauncher Pack", "1.20.1", instance_dir, ("forge", "47.4.0"))
    first = b"first"
    second = b"second"
    registry = {
        "safeName": "ExamplePack",
        "versionName": "2.0.0",
        "managedFiles": [
            {
                "fileId": "1",
                "fileName": "first.jar",
                "path": "mods/first.jar",
                "md5": md5(first, usedforsecurity=False).hexdigest(),
                "size": len(first),
                "urls": ["https://cdn.example/first.jar"],
                "pendingDownload": True,
            },
            {
                "fileId": "2",
                "fileName": "second.jar",
                "path": "mods/second.jar",
                "md5": md5(second, usedforsecurity=False).hexdigest(),
                "size": len(second),
                "urls": ["https://cdn.example/second.jar"],
                "pendingDownload": True,
            },
        ],
    }
    payloads = {"first.jar": first, "second.jar": second}
    requests = []
    saved: list[dict] = []
    events = []

    monkeypatch.setattr(ATLauncherPackRegistry, "load", staticmethod(lambda _instance: registry))
    monkeypatch.setattr(ATLauncherPackRegistry, "save", staticmethod(lambda _instance, data: saved.append(data)))
    monkeypatch.setattr(download_manager, "verify", lambda path, size, hashes: Path(path).is_file() and Path(path).read_bytes() == payloads[Path(path).name])
    monkeypatch.setattr(ModManager, "ensure_modifiable", staticmethod(lambda *_args, **_kwargs: None))

    def download(request, reporter=None, progress_stage=None, progress_message=""):
        requests.append(request)
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        content = payloads[request.expected_filename]
        if reporter is not None:
            reporter.bytes(progress_stage, request.expected_filename, len(content), len(content), bytes_per_second=2_000_000)
        request.destination.write_bytes(content)
        return request.destination

    monkeypatch.setattr("src.core.atlauncher.atlauncher_content_manager.artifact_download_service.download", download)

    assert ATLauncherContentManager.ensure(instance, ProgressReporter(events.append), launch_lock_token="owned") == ()

    assert [request.provider for request in requests] == ["atlauncher", "atlauncher"]
    assert (instance_dir / "mods" / "first.jar").read_bytes() == first
    assert (instance_dir / "mods" / "second.jar").read_bytes() == second
    assert all(entry["pendingDownload"] is False for entry in saved[-1]["managedFiles"])
    progress = [event for event in events if event.stage is ProgressStage.DOWNLOADING_MODS]
    assert progress
    assert all(event.unit is ProgressUnit.FILES for event in progress)
    assert all(event.message == "Downloading ATLauncher pack files..." for event in progress)
    assert all("first.jar" not in event.message and "second.jar" not in event.message for event in progress)
    assert progress[-1].current == 2
    assert progress[-1].total == 2


def test_safe_extract_zip_rejects_traversal_and_extracts_valid_files(tmp_path) -> None:
    destination = tmp_path / "instance"
    destination.mkdir()
    valid = tmp_path / "valid.zip"
    with zipfile.ZipFile(valid, "w") as archive:
        archive.writestr("config/example.cfg", "enabled=true")

    ATLauncherContentManager._safe_extract_zip(valid, destination)

    assert (destination / "config" / "example.cfg").read_text(encoding="utf-8") == "enabled=true"

    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside.txt", "nope")

    with pytest.raises(RuntimeError, match="Unsafe path"):
        ATLauncherContentManager._safe_extract_zip(unsafe, destination)
    assert not (tmp_path / "outside.txt").exists()
