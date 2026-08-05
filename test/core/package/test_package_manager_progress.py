import json
import zipfile
from pathlib import Path

from src.core.fs.paths import Paths
from src.core.package.package_manager import PackageManager
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_unit import ProgressUnit


def package_metadata() -> dict:
    return {
        "format": "mcwpack",
        "format_version": 1,
        "package_type": "instance",
        "launcher_name": "mcw-launcher",
        "launcher_version": "v0.5.1-rc.1",
        "created_at": "2026-07-16T00:00:00+00:00",
        "include_saves": False,
    }


def determinate_events(events: list[object]) -> list[object]:
    return [event for event in events if getattr(event, "current", None) is not None and getattr(event, "total", None) is not None]


def assert_monotonic_byte_progress(events: list[object], stage: ProgressStage) -> None:
    progress = determinate_events(events)
    assert progress
    assert all(event.stage is stage for event in progress)
    assert all(event.unit is ProgressUnit.BYTES for event in progress)
    currents = [event.current for event in progress]
    assert currents == sorted(currents)
    assert progress[0].current == 0
    assert progress[-1].current == progress[-1].total
    assert progress[-1].percentage == 100


def test_export_reports_byte_progress_and_skips_saves(tmp_path: Path, monkeypatch) -> None:
    instance_dir = tmp_path / "instance"
    (instance_dir / "mods").mkdir(parents=True)
    (instance_dir / "saves" / "world").mkdir(parents=True)
    (instance_dir / "instance.json").write_text('{"name":"Progress Pack"}', encoding="utf-8")
    (instance_dir / "mods" / "large.jar").write_bytes(b"m" * (PackageManager.COPY_CHUNK_SIZE * 2 + 123))
    (instance_dir / "saves" / "world" / "level.dat").write_bytes(b"save")
    instance = Instance(instance_id="progress", name="Progress Pack", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))
    monkeypatch.setattr(Paths, "load_instance_dir", staticmethod(lambda _name: instance_dir))
    events: list[object] = []

    output = PackageManager.export_instance(instance, tmp_path / "progress.mcwpack", include_saves=False, on_progress=events.append)

    assert output.exists()
    assert not output.with_name(f".{output.name}.part").exists()
    with zipfile.ZipFile(output, "r") as archive:
        assert "mods/large.jar" in archive.namelist()
        assert "saves/world/level.dat" not in archive.namelist()
    assert events[0].stage is ProgressStage.EXPORTING_INSTANCE
    assert events[0].current is None
    assert_monotonic_byte_progress(events, ProgressStage.EXPORTING_INSTANCE)
    assert any("mods/large.jar" in event.message for event in events)


def test_export_does_not_include_package_when_saved_inside_instance(tmp_path: Path, monkeypatch) -> None:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    (instance_dir / "instance.json").write_text("{}", encoding="utf-8")
    instance = Instance(instance_id="self", name="Self Export", version_id="1.21.1", instance_dir=instance_dir, mod_loader=("vanilla", "-1"))
    monkeypatch.setattr(Paths, "load_instance_dir", staticmethod(lambda _name: instance_dir))
    output = instance_dir / "self-export.mcwpack"

    PackageManager.export_instance(instance, output)

    with zipfile.ZipFile(output, "r") as archive:
        assert "self-export.mcwpack" not in archive.namelist()
        assert ".self-export.mcwpack.part" not in archive.namelist()


def test_import_reports_byte_progress(tmp_path: Path) -> None:
    package = tmp_path / "progress.mcwpack"
    payload = b"x" * (PackageManager.COPY_CHUNK_SIZE * 2 + 321)
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("package.json", json.dumps(package_metadata()))
        archive.writestr("instance.json", b"{}")
        archive.writestr("mods/large.jar", payload)
    events: list[object] = []
    output = tmp_path / "output"

    PackageManager.extract(package, output, events.append)

    assert (output / "mods" / "large.jar").read_bytes() == payload
    assert events[0].stage is ProgressStage.IMPORTING_INSTANCE
    assert events[0].current is None
    assert_monotonic_byte_progress(events, ProgressStage.IMPORTING_INSTANCE)
    assert any("mods/large.jar" in event.message for event in events)
