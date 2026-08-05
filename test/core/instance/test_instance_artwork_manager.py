from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_artwork_manager import InstanceArtworkManager
from src.core.instance.instance_manager import InstanceManager
from src.core.network.artifact_download_service import artifact_download_service
from src.models.instance.instance import Instance


PNG_BYTES = b"\x89PNG\r\n\x1a\nprovider-artwork"


@pytest.fixture
def artwork_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    instances = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", instances)
    monkeypatch.setattr(Paths, "INSTANCE_LOCKS_ROOT", instances / ".runtime" / "locks")
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    return instances


def test_provider_artwork_is_cached_and_stored_inside_instance(artwork_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = InstanceManager.create("Provider Pack", SimpleNamespace(id="1.20.1"))
    downloads = []

    def download(request, **_kwargs):
        downloads.append(request.destination)
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        request.destination.write_bytes(PNG_BYTES)
        return SimpleNamespace(path=request.destination)

    monkeypatch.setattr(artifact_download_service, "download", download)

    assert InstanceArtworkManager.apply_provider_artwork(instance, "modrinth", "pack-id", "https://cdn.example/icon.png") is True
    updated = InstanceManager.load(instance.name)
    assert updated.icon == ".mcw/instance-icon.png"
    assert (updated.instance_dir / updated.icon).read_bytes() == PNG_BYTES
    metadata = json.loads((updated.instance_dir / "instance.json").read_text(encoding="utf-8"))
    assert metadata["icon_origin"] == {"provider": "modrinth", "project_id": "pack-id"}
    assert len(downloads) == 1

    monkeypatch.setattr(artifact_download_service, "download", lambda *_args, **_kwargs: pytest.fail("cache was not reused"))
    assert InstanceArtworkManager.apply_provider_artwork(updated, "modrinth", "pack-id", "https://cdn.example/icon.png") is True


def test_invalid_provider_artwork_keeps_default_icon(artwork_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = InstanceManager.create("Invalid Artwork", SimpleNamespace(id="1.20.1"))

    def download(request, **_kwargs):
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        request.destination.write_bytes(b"not-an-image")
        return SimpleNamespace(path=request.destination)

    monkeypatch.setattr(artifact_download_service, "download", download)

    assert InstanceArtworkManager.apply_provider_artwork(instance, "curseforge", 123, "https://cdn.example/not-image") is False
    assert InstanceManager.load(instance.name).icon == InstanceManager.DEFAULT_ICON


def test_manual_icon_overrides_provider_origin_and_reset_restores_default(artwork_paths: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Manual Artwork", SimpleNamespace(id="1.20.1"))
    source = tmp_path / "manual.png"
    source.write_bytes(PNG_BYTES)

    InstanceManager.set_icon(instance.name, source, origin={"provider": "curseforge", "project_id": "42"})
    InstanceManager.set_icon(instance.name, source)
    metadata = json.loads((instance.instance_dir / "instance.json").read_text(encoding="utf-8"))
    assert metadata["icon_origin"] == {"provider": "custom"}

    InstanceManager.reset_icon(instance.name)
    metadata = json.loads((instance.instance_dir / "instance.json").read_text(encoding="utf-8"))
    assert metadata["icon_origin"] == {"provider": "default"}


def test_embedded_archive_icon_is_validated_and_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zipfile import ZipFile

    root = tmp_path / "Artwork"
    root.mkdir()
    instance = Instance("artwork", "Artwork", "1.21.1", root, ("fabric", "0.16.0"))
    package = tmp_path / "pack.mrpack"
    with ZipFile(package, "w") as archive:
        archive.writestr("mcw/instance-icon.png", PNG_BYTES)
    calls: list[tuple[str, bytes, dict]] = []

    def set_icon(name: str, source: Path, origin=None):
        calls.append((name, Path(source).read_bytes(), dict(origin or {})))
        return instance

    monkeypatch.setattr(InstanceManager, "set_icon", staticmethod(set_icon))
    with ZipFile(package) as archive:
        applied = InstanceArtworkManager.apply_embedded_archive_artwork(instance, archive)

    assert applied is True
    assert calls[0][0] == instance.name
    assert calls[0][1] == PNG_BYTES
    assert calls[0][2]["member"] == "mcw/instance-icon.png"


def test_embedded_archive_icon_rejects_invalid_image_without_failing_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from zipfile import ZipFile
    root = tmp_path / "Artwork"
    root.mkdir()
    instance = Instance("artwork", "Artwork", "1.21.1", root, ("fabric", "0.16.0"))
    package = tmp_path / "pack.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr("mcw/instance-icon.png", b"not-an-image")
    monkeypatch.setattr(InstanceManager, "set_icon", staticmethod(lambda *_args, **_kwargs: pytest.fail("invalid image must not be applied")))

    with ZipFile(package) as archive:
        assert InstanceArtworkManager.apply_embedded_archive_artwork(instance, archive) is False
