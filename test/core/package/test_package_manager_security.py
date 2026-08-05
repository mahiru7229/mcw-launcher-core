import json
import stat
import zipfile
from pathlib import Path

import pytest

from src.core.package.package_manager import PackageManager


def metadata() -> dict:
    return {
        "format": "mcwpack",
        "format_version": 1,
        "package_type": "instance",
        "launcher_name": "mcw-launcher",
        "launcher_version": "v0.5.1-rc.1",
        "created_at": "2026-07-16T00:00:00+00:00",
        "include_saves": False,
    }


def make_package(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("package.json", json.dumps(metadata()))
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


def test_extract_rejects_parent_path_traversal(tmp_path: Path) -> None:
    package = make_package(tmp_path / "unsafe.mcwpack", {"../outside.txt": b"escape"})
    output = tmp_path / "output"

    with pytest.raises(RuntimeError, match="Invalid package path"):
        PackageManager.extract(package, output)

    assert not (tmp_path / "outside.txt").exists()


def test_extract_rejects_symbolic_links(tmp_path: Path) -> None:
    package = tmp_path / "symlink.mcwpack"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("package.json", json.dumps(metadata()))
        info = zipfile.ZipInfo("mods/link.jar")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../outside.jar")

    with pytest.raises(RuntimeError, match="symbolic links"):
        PackageManager.extract(package, tmp_path / "output")


def test_extract_rejects_case_insensitive_duplicate_paths(tmp_path: Path) -> None:
    package = make_package(tmp_path / "duplicates.mcwpack", {"mods/Example.jar": b"one", "MODS/example.jar": b"two"})

    with pytest.raises(RuntimeError, match="duplicate path"):
        PackageManager.extract(package, tmp_path / "output")


def test_extract_valid_package(tmp_path: Path) -> None:
    package = make_package(tmp_path / "valid.mcwpack", {"instance.json": b"{}", "mods/example.jar": b"mod"})
    output = tmp_path / "output"

    package_metadata = PackageManager.extract(package, output)

    assert package_metadata.format == "mcwpack"
    assert (output / "mods" / "example.jar").read_bytes() == b"mod"


def test_extract_rejects_windows_reserved_paths(tmp_path: Path) -> None:
    package = make_package(tmp_path / "reserved.mcwpack", {"mods/CON.jar": b"invalid"})

    with pytest.raises(RuntimeError, match="Invalid Windows package path"):
        PackageManager.extract(package, tmp_path / "output")


def test_extract_validates_all_members_before_writing_files(tmp_path: Path) -> None:
    package = tmp_path / "late-invalid.mcwpack"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("package.json", json.dumps(metadata()))
        archive.writestr("mods/valid.jar", b"valid")
        archive.writestr("../outside.jar", b"escape")
    output = tmp_path / "output"

    with pytest.raises(RuntimeError, match="Invalid package path"):
        PackageManager.extract(package, output)

    assert not (output / "mods" / "valid.jar").exists()


def test_extract_deduplicates_identical_archive_members(tmp_path: Path) -> None:
    package = tmp_path / "identical-duplicates.mcwpack"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("package.json", json.dumps(metadata()))
        archive.writestr("instance.json", b"{}")
        archive.writestr("mods/example.jar", b"same-content")
        archive.writestr("mods/example.jar", b"same-content")
    output = tmp_path / "output"

    PackageManager.extract(package, output)

    assert (output / "mods" / "example.jar").read_bytes() == b"same-content"


def test_extract_rejects_conflicting_duplicate_archive_members(tmp_path: Path) -> None:
    package = tmp_path / "conflicting-duplicates.mcwpack"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("package.json", json.dumps(metadata()))
        archive.writestr("instance.json", b"{}")
        archive.writestr("mods/example.jar", b"first")
        archive.writestr("mods/example.jar", b"second")

    with pytest.raises(RuntimeError, match="conflicting duplicate path"):
        PackageManager.extract(package, tmp_path / "output")
