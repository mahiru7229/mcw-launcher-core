from pathlib import Path
import hashlib

from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.models.instance.instance import Instance


def test_scans_missing_and_modified_managed_files(tmp_path):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))
    content = b"original"
    target = instance_dir / "config" / "pack.json"
    target.parent.mkdir()
    target.write_bytes(content)
    ModrinthPackRegistry.save(instance_dir, {"projectId": "pack", "versionId": "v1", "managedFiles": [{"path": "config/pack.json", "sha1": hashlib.sha1(content).hexdigest(), "size": len(content), "source": "overrides"}, {"path": "mods/missing.jar", "sha1": "abc", "source": "download"}]})
    target.write_bytes(b"changed")

    report = ModrinthPackRegistry.scan(instance)

    assert report.modified_count == 1
    assert report.missing_count == 1


def test_scan_reuses_verification_cache_for_unchanged_files(tmp_path, monkeypatch):
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    instance = Instance(instance_id="id", name="Pack", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))
    content = b"cached-content"
    target = instance_dir / "mods" / "cached.jar"
    target.parent.mkdir()
    target.write_bytes(content)
    ModrinthPackRegistry.save(instance_dir, {"projectId": "pack", "versionId": "v1", "managedFiles": [{"path": "mods/cached.jar", "sha1": hashlib.sha1(content).hexdigest(), "size": len(content), "source": "download"}]})

    first = ModrinthPackRegistry.scan(instance)
    assert first.hashed_files == 1
    assert first.cache_hits == 0

    from src.core.modrinth.modrinth_downloader import ModrinthDownloader
    monkeypatch.setattr(ModrinthDownloader, "verify", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cached file should not be re-hashed")))

    second = ModrinthPackRegistry.scan(instance)
    assert second.changes == ()
    assert second.cache_hits == 1
    assert second.hashed_files == 0
