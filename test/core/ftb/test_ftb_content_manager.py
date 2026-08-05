from pathlib import Path

from src.core.ftb.ftb_content_manager import FTBContentManager
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.network.download_manager import download_manager
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_unit import ProgressUnit


def test_ensure_downloads_deferred_files_with_aggregate_progress(tmp_path, monkeypatch) -> None:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance("id", "FTB Pack", "1.20.1", instance_dir, ("forge", "47.4.0"))
    registry = {
        "projectId": 25,
        "versionId": 101,
        "managedFiles": [
            {
                "fileId": 1,
                "fileName": "first.jar",
                "path": "mods/first.jar",
                "sha1": "a" * 40,
                "size": 3,
                "urls": ["https://primary.example/first.jar", "https://mirror.example/first.jar"],
                "pendingDownload": True,
            },
            {
                "fileId": 2,
                "fileName": "second.jar",
                "path": "mods/second.jar",
                "sha1": "b" * 40,
                "size": 3,
                "urls": ["https://primary.example/second.jar"],
                "pendingDownload": True,
            },
        ],
    }
    saved: list[dict] = []
    requests = []
    events = []

    monkeypatch.setattr(FTBPackRegistry, "load", staticmethod(lambda _instance: registry))
    monkeypatch.setattr(FTBPackRegistry, "save", staticmethod(lambda _instance, data: saved.append(data)))
    monkeypatch.setattr(download_manager, "verify", lambda path, *_args, **_kwargs: Path(path).is_file())
    monkeypatch.setattr(ModManager, "ensure_modifiable", staticmethod(lambda *_args, **_kwargs: None))

    def download(request, reporter=None, progress_stage=None, progress_message=""):
        requests.append(request)
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        if reporter is not None:
            reporter.bytes(progress_stage, request.expected_filename, 1, 3, bytes_per_second=2_500_000)
        request.destination.write_bytes(b"mod")
        return request.destination

    monkeypatch.setattr("src.core.ftb.ftb_content_manager.artifact_download_service.download", download)

    assert FTBContentManager.ensure(instance, ProgressReporter(events.append), launch_lock_token="owned") == ()

    assert [request.urls for request in requests] == [
        ("https://primary.example/first.jar", "https://mirror.example/first.jar"),
        ("https://primary.example/second.jar",),
    ]
    assert (instance_dir / "mods" / "first.jar").read_bytes() == b"mod"
    assert (instance_dir / "mods" / "second.jar").read_bytes() == b"mod"
    assert saved[-1]["managedFiles"][0]["pendingDownload"] is False
    download_events = [event for event in events if event.stage is ProgressStage.DOWNLOADING_MODS]
    assert download_events
    assert all(event.unit is ProgressUnit.FILES for event in download_events)
    assert all(event.message == "Downloading modpack mods..." for event in download_events)
    assert all("first.jar" not in event.message and "second.jar" not in event.message for event in download_events)
    assert any((event.bytes_per_second or 0) > 0 for event in download_events)
    assert download_events[-1].current == 2
    assert download_events[-1].total == 2
