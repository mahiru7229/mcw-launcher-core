from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json

from src.core.package.portable_content_manager import PortableContentManager


def test_finalize_disabled_moves_downloaded_mod_and_clears_registry(tmp_path: Path) -> None:
    instance = SimpleNamespace(instance_dir=tmp_path)
    active = tmp_path / "mods" / "example.jar"
    active.parent.mkdir(parents=True)
    active.write_bytes(b"example")
    registry = tmp_path / ".mcw" / PortableContentManager.DISABLED_FILE_NAME
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({
        "schemaVersion": 1,
        "files": [{
            "targetPath": "mods/example.jar.disabled",
            "fileName": "example.jar",
            "size": active.stat().st_size,
            "hashes": {"sha1": hashlib.sha1(active.read_bytes(), usedforsecurity=False).hexdigest()},
        }],
    }), encoding="utf-8")

    PortableContentManager.finalize_disabled(instance)

    assert not active.exists()
    assert (tmp_path / "mods" / "example.jar.disabled").read_bytes() == b"example"
    assert not registry.exists()


def test_prefetch_referenced_falls_back_to_second_provider(tmp_path: Path, monkeypatch) -> None:
    from src.models.curseforge.file import CurseForgeFile
    from src.models.modrinth.version import ModrinthFile, ModrinthVersion

    payload = b"fallback file"
    sha1 = hashlib.sha1(payload, usedforsecurity=False).hexdigest()
    instance = SimpleNamespace(instance_dir=tmp_path)
    registry = tmp_path / ".mcw" / PortableContentManager.REFERENCED_FILE_NAME
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({
        "schemaVersion": 1,
        "files": [{
            "targetPath": "mods/example.jar",
            "fileName": "example.jar",
            "size": len(payload),
            "hashes": {"sha1": sha1},
            "sources": [
                {"provider": "modrinth", "versionId": "bad-version", "priority": 10},
                {"provider": "curseforge", "projectId": "123", "fileId": "456", "priority": 20},
            ],
        }],
    }), encoding="utf-8")

    bad_version = ModrinthVersion(
        version_id="bad-version",
        project_id="bad-project",
        name="Bad",
        version_number="1",
        version_type="release",
        game_versions=("1.21.1",),
        loaders=("fabric",),
        files=(ModrinthFile(url="https://cdn.modrinth.com/bad", filename="example.jar", sha1="0" * 40, sha512="", size=len(payload)),),
    )
    curseforge_file = CurseForgeFile(
        file_id=456,
        project_id=123,
        display_name="Exact",
        file_name="example.jar",
        release_type="release",
        file_date="",
        file_length=len(payload),
        download_url="https://mediafilez.forgecdn.net/example.jar",
        sha1=sha1,
        game_versions=("1.21.1",),
        dependencies=(),
    )
    monkeypatch.setattr("src.core.package.portable_content_manager.ModrinthClient.get_version", lambda _version: bad_version)
    monkeypatch.setattr("src.core.package.portable_content_manager.CurseForgeClient.get_file", lambda _project, _file: curseforge_file)

    def fake_download(_file, destination: Path, **_kwargs):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return destination

    monkeypatch.setattr("src.core.package.portable_content_manager.CurseForgeDownloader.download_file", fake_download)

    PortableContentManager.prefetch_referenced(instance)

    assert (tmp_path / "mods" / "example.jar").read_bytes() == payload
    assert not registry.exists()
