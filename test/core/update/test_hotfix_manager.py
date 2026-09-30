from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import httpx
import pytest

from src.core.update.hotfix_manager import (
    HotfixEntry,
    HotfixError,
    HotfixManager,
    HotfixNetworkError,
    HotfixSecurityError,
    HotfixState,
    HotfixVerificationError,
)
from src.core.update.versioning import LauncherVersion


def _create_zip_bytes(file_entries: dict[str, bytes]) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in file_entries.items():
            zf.writestr(path, data)
    raw_bytes = buffer.getvalue()
    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    return raw_bytes, sha256


def test_hotfix_entry_version_parsing() -> None:
    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Patch crash",
        enabled=True,
        download_url="https://example.com/hf1.zip",
        sha256="abc",
        size_bytes=100,
    )
    assert entry.base_launcher_version == LauncherVersion(1, 7, 0, revision=0)
    assert entry.target_launcher_version == LauncherVersion(1, 7, 0, revision=1)
    assert entry.target_launcher_version > entry.base_launcher_version


def test_fetch_manifest_valid(tmp_path: Path) -> None:
    manifest_data = {
        "schema_version": 1,
        "service": "mcw-hotfix-network",
        "active_hotfixes": [
            {
                "base_version": "1.7.0",
                "target_version": "1.7.0.1",
                "hotfix_id": 1,
                "release_tag": "v1.7.0.1",
                "description": "Fix bug",
                "enabled": True,
                "download_url": "https://example.com/v1.7.0.1.zip",
                "sha256": "abcdef123456",
                "size_bytes": 1024,
                "clean_on_upgrade": True,
                "target_modules": ["src.core.update"],
            }
        ],
    }

    def transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=manifest_data)

    client = httpx.Client(transport=httpx.MockTransport(transport_handler))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    entries = manager.fetch_manifest()
    assert len(entries) == 1
    assert entries[0].target_version == "1.7.0.1"
    assert entries[0].hotfix_id == 1
    assert entries[0].enabled is True


def test_fetch_manifest_invalid_schema(tmp_path: Path) -> None:
    def transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"schema_version": 99})

    client = httpx.Client(transport=httpx.MockTransport(transport_handler))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    with pytest.raises(HotfixError, match="Unsupported manifest schema_version"):
        manager.fetch_manifest()


def test_check_for_hotfix_selection(tmp_path: Path) -> None:
    manifest_data = {
        "schema_version": 1,
        "active_hotfixes": [
            {
                "base_version": "1.7.0",
                "target_version": "1.7.0.1",
                "hotfix_id": 1,
                "enabled": True,
                "download_url": "https://example.com/1.zip",
                "sha256": "111",
            },
            {
                "base_version": "1.7.0",
                "target_version": "1.7.0.2",
                "hotfix_id": 2,
                "enabled": True,
                "download_url": "https://example.com/2.zip",
                "sha256": "222",
            },
            {
                "base_version": "1.7.0",
                "target_version": "1.7.0.3",
                "hotfix_id": 3,
                "enabled": False,  # disabled hotfix
                "download_url": "https://example.com/3.zip",
                "sha256": "333",
            },
            {
                "base_version": "1.7.1",
                "target_version": "1.7.1.1",
                "hotfix_id": 1,
                "enabled": True,
                "download_url": "https://example.com/171.zip",
                "sha256": "444",
            },
        ],
    }

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=manifest_data)))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    # Base 1.7.0 with no hotfix installed -> should choose 1.7.0.2 (id=2, latest enabled)
    best = manager.check_for_hotfix("1.7.0", current_hotfix_id=0)
    assert best is not None
    assert best.target_version == "1.7.0.2"
    assert best.hotfix_id == 2

    # If already on hotfix_id=2 -> no newer enabled hotfix (id=3 is disabled)
    assert manager.check_for_hotfix("1.7.0", current_hotfix_id=2) is None

    # Base 1.7.1 -> should choose 1.7.1.1
    best_171 = manager.check_for_hotfix("1.7.1", current_hotfix_id=0)
    assert best_171 is not None
    assert best_171.target_version == "1.7.1.1"


def test_apply_hotfix_success_and_sys_path_injection(tmp_path: Path) -> None:
    patch_code = b"PATCHED_CONSTANT = 'HOTFIX_APPLIED_1_7_0_1'\n"
    zip_bytes, sha256 = _create_zip_bytes({"test_patch_mod.py": patch_code})

    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Fix test issue",
        enabled=True,
        download_url="https://example.com/patch.zip",
        sha256=sha256,
        size_bytes=len(zip_bytes),
        target_modules=["test_patch_mod"],
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    state = manager.apply_hotfix(entry)
    assert state.target_version == "1.7.0.1"
    assert state.applied_hotfix_id == 1

    # Verify extracted file exists in live/
    live_patch_file = manager.live_dir / "test_patch_mod.py"
    assert live_patch_file.is_file()
    assert live_patch_file.read_bytes() == patch_code

    # Effective version
    assert manager.get_effective_version("1.7.0") == "1.7.0.1"
    assert manager.get_effective_version("1.7.1") == "1.7.1"

    # Test bootstrap sys.path injection
    injected = HotfixManager.bootstrap_sys_path(root_directory=tmp_path, current_base_version="1.7.0")
    assert injected is True
    assert str(manager.live_dir.resolve()) == sys.path[0]


def test_apply_hotfix_checksum_failure(tmp_path: Path) -> None:
    zip_bytes, _ = _create_zip_bytes({"file.py": b"content"})
    wrong_sha256 = "0000000000000000000000000000000000000000000000000000000000000000"

    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Test wrong hash",
        enabled=True,
        download_url="https://example.com/patch.zip",
        sha256=wrong_sha256,
        size_bytes=len(zip_bytes),
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    with pytest.raises(HotfixVerificationError, match="Checksum mismatch"):
        manager.apply_hotfix(entry)

    # Live dir and state must not be created
    assert not manager.live_dir.exists()
    assert not manager.state_file.exists()


def test_apply_hotfix_zip_slip_rejection(tmp_path: Path) -> None:
    # Build a malicious zip with traversal path
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("../../escape.txt", b"malicious content")
    zip_bytes = buffer.getvalue()
    sha256 = hashlib.sha256(zip_bytes).hexdigest()

    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Malicious traversal",
        enabled=True,
        download_url="https://example.com/evil.zip",
        sha256=sha256,
        size_bytes=len(zip_bytes),
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    with pytest.raises(HotfixSecurityError, match="Zip Slip"):
        manager.apply_hotfix(entry)

    assert not manager.live_dir.exists()


def test_cleanup_on_base_version_upgrade(tmp_path: Path) -> None:
    zip_bytes, sha256 = _create_zip_bytes({"patch.py": b"print(1)"})
    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Patch 1.7.0.1",
        enabled=True,
        download_url="https://example.com/p.zip",
        sha256=sha256,
        size_bytes=len(zip_bytes),
        clean_on_upgrade=True,
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)
    manager.apply_hotfix(entry)

    assert manager.live_dir.is_dir()
    assert manager.state_file.is_file()

    # If launcher starts with current base 1.7.1 -> base version changed, cleanup must trigger!
    cleaned = HotfixManager.bootstrap_sys_path(root_directory=tmp_path, current_base_version="1.7.1")
    assert cleaned is False
    assert not manager.live_dir.exists()
    assert not manager.state_file.exists()


def test_rollback(tmp_path: Path) -> None:
    zip_bytes, sha256 = _create_zip_bytes({"mod.py": b"x=1"})
    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Patch",
        enabled=True,
        download_url="https://example.com/p.zip",
        sha256=sha256,
        size_bytes=len(zip_bytes),
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)
    manager.apply_hotfix(entry)

    assert manager.live_dir.is_dir()
    assert manager.state_file.is_file()

    assert manager.rollback() is True
    assert not manager.live_dir.exists()
    assert not manager.state_file.exists()
    assert manager.get_effective_version("1.7.0") == "1.7.0"


def test_prerelease_base_version_matching(tmp_path: Path) -> None:
    manifest_data = {
        "schema_version": 1,
        "active_hotfixes": [
            {
                "base_version": "1.7.0",
                "target_version": "1.7.0.1",
                "hotfix_id": 1,
                "enabled": True,
                "download_url": "https://example.com/1.zip",
                "sha256": "111",
            },
        ],
    }

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=manifest_data)))
    manager = HotfixManager(root_directory=tmp_path, client=client)

    # A launcher running 1.7.0-alpha.1 should match base 1.7.0
    best = manager.check_for_hotfix("1.7.0-alpha.1", current_hotfix_id=0)
    assert best is not None
    assert best.target_version == "1.7.0.1"


def test_meta_path_finder_submodule_interception(tmp_path: Path) -> None:
    patch_code = b"FLAG_VALUE = 'patched_from_hotfix'\n"
    zip_bytes, sha256 = _create_zip_bytes({"testpkg/subpkg/worker.py": patch_code})

    entry = HotfixEntry(
        base_version="1.7.0",
        target_version="1.7.0.1",
        hotfix_id=1,
        release_tag="v1.7.0.1",
        description="Patch worker",
        enabled=True,
        download_url="https://example.com/p.zip",
        sha256=sha256,
        size_bytes=len(zip_bytes),
    )

    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=zip_bytes)))
    manager = HotfixManager(root_directory=tmp_path, client=client)
    manager.apply_hotfix(entry)

    # Clean any leftover sys.modules
    for mod in list(sys.modules.keys()):
        if mod.startswith("testpkg"):
            del sys.modules[mod]

    HotfixManager.bootstrap_sys_path(root_directory=tmp_path, current_base_version="1.7.0")

    import testpkg.subpkg.worker as worker
    assert getattr(worker, "FLAG_VALUE") == "patched_from_hotfix"
    assert str(manager.live_dir.resolve()) in str(Path(worker.__file__).resolve())

    # Rollback clears finder
    assert manager.rollback() is True
    from src.core.update.hotfix_manager import HotfixMetaPathFinder
    assert not any(isinstance(f, HotfixMetaPathFinder) for f in sys.meta_path)


