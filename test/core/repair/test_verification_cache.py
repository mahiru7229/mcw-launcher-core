from pathlib import Path
import hashlib
import json

from src.core.repair.verification_cache import VerificationCache


def test_quick_check_uses_size_and_full_check_populates_cache(tmp_path: Path) -> None:
    target = tmp_path / "client.jar"
    target.write_bytes(b"minecraft-client")
    expected = hashlib.sha1(target.read_bytes(), usedforsecurity=False).hexdigest()
    cache = VerificationCache(tmp_path / "verification.json")

    quick = cache.verify("client", target, target.stat().st_size, expected, force_hash=False)
    assert quick.valid is True
    assert quick.cache_hit is False
    assert quick.hashed is False
    assert quick.reason == "size_only"

    full = cache.verify("client", target, target.stat().st_size, expected, force_hash=True)
    assert full.valid is True
    assert full.hashed is True
    cache.save()

    loaded = VerificationCache(tmp_path / "verification.json")
    reused = loaded.verify("client", target, target.stat().st_size, expected, force_hash=False)
    assert reused.valid is True
    assert reused.cache_hit is True
    assert reused.hashed is False


def test_cache_invalidates_when_file_changes(tmp_path: Path) -> None:
    target = tmp_path / "library.jar"
    target.write_bytes(b"first")
    expected = hashlib.sha1(b"first", usedforsecurity=False).hexdigest()
    path = tmp_path / "verification.json"
    cache = VerificationCache(path)
    assert cache.verify("library", target, 5, expected, force_hash=True).valid
    cache.save()

    target.write_bytes(b"wrong!")
    loaded = VerificationCache(path)
    result = loaded.verify("library", target, 5, expected, force_hash=False)
    assert result.valid is False
    assert result.reason == "size_mismatch"


def test_cache_is_written_atomically(tmp_path: Path) -> None:
    target = tmp_path / "asset"
    target.write_bytes(b"asset")
    expected = hashlib.sha1(b"asset", usedforsecurity=False).hexdigest()
    path = tmp_path / "cache.json"
    cache = VerificationCache(path)
    cache.verify("asset", target, 5, expected, force_hash=True)
    cache.save()

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == 1
    assert "asset" in data["records"]
    assert not path.with_suffix(".json.part").exists()
