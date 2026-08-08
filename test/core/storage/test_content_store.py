from pathlib import Path
import os

from src.core.fs.paths import Paths
from src.core.storage.content_store import ContentStore


def test_adopt_publishes_provider_binary_without_changing_contents(tmp_path: Path) -> None:
    with Paths.configured(tmp_path):
        source = Paths.CACHE_ROOT / "content" / "curseforge" / "files" / "10" / "20" / "example.jar"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"managed-provider-artifact" * 128)

        result = ContentStore.adopt(source)

        assert result.path == source
        assert result.canonical_path.is_file()
        assert result.canonical_path.read_bytes() == source.read_bytes()
        assert result.canonical_path == Paths.content_store_blob(result.sha256)
        if result.hardlinked:
            assert os.path.samefile(source, result.canonical_path)


def test_materialize_uses_canonical_content_and_atomic_destination(tmp_path: Path) -> None:
    with Paths.configured(tmp_path):
        source = Paths.CACHE_ROOT / "content" / "modrinth" / "files" / "project" / "version" / "example.jar"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"same immutable artifact" * 512)
        destination = Paths.INSTANCES_ROOT / "Example" / "mods" / source.name

        result = ContentStore.materialize(source, destination)

        assert destination.read_bytes() == source.read_bytes()
        assert result.path == destination
        assert result.canonical_path.is_file()
        assert not list(destination.parent.glob("*.materializing"))
        if result.hardlinked:
            assert os.path.samefile(destination, result.canonical_path)
            assert os.path.samefile(source, result.canonical_path)


def test_materialize_falls_back_to_copy_when_hardlinks_are_unavailable(tmp_path: Path, monkeypatch) -> None:
    with Paths.configured(tmp_path):
        source = tmp_path / "provider.jar"
        source.write_bytes(b"fallback")
        destination = tmp_path / "instance" / "mods" / "provider.jar"
        original_link = os.link

        def fail_link(src, dst, *args, **kwargs):
            raise OSError("hardlinks unavailable")

        monkeypatch.setattr(os, "link", fail_link)
        try:
            result = ContentStore.materialize(source, destination)
        finally:
            monkeypatch.setattr(os, "link", original_link)

        assert destination.read_bytes() == b"fallback"
        assert result.hardlinked is False
        assert result.canonical_path.is_file()


def test_adopt_keeps_concurrently_published_canonical_blob(tmp_path: Path, monkeypatch) -> None:
    with Paths.configured(tmp_path):
        source = tmp_path / "provider.jar"
        payload = b"concurrent-provider-artifact" * 256
        source.write_bytes(payload)
        digest = ContentStore.sha256(source)
        target = Paths.content_store_blob(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        original_link = os.link

        def publish_then_report_exists(src, dst, *args, **kwargs):
            if Path(dst) == target and not target.exists():
                target.write_bytes(payload)
                raise FileExistsError(str(target))
            return original_link(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, "link", publish_then_report_exists)
        result = ContentStore.adopt(source)

        assert result.canonical_path == target
        assert target.read_bytes() == payload
        assert ContentStore.sha256(target) == digest
