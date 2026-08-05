from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.package.package_manager import PackageManager


@pytest.fixture
def instance_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", root)
    return root


def test_mcwpack_contains_managed_instance_icon(instance_root: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Pack Icon", SimpleNamespace(id="1.20.1"))
    source = tmp_path / "pack-icon.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\npack-icon")
    instance = InstanceManager.set_icon(instance.name, source)
    output = tmp_path / "pack-icon.mcwpack"

    PackageManager.export_instance(instance, output)

    with ZipFile(output) as archive:
        assert ".mcw/instance-icon.png" in archive.namelist()
        assert archive.read(".mcw/instance-icon.png") == source.read_bytes()
        package = json.loads(archive.read("package.json"))
        metadata = json.loads(archive.read("instance.json"))
    assert package["instance_name"] == "Pack Icon"
    assert package["instance_icon"] == ".mcw/instance-icon.png"
    assert metadata["icon"] == ".mcw/instance-icon.png"


def test_export_internalizes_legacy_external_icon(instance_root: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Legacy Icon", SimpleNamespace(id="1.20.1"))
    external = tmp_path / "legacy.ico"
    external.write_bytes(b"legacy-icon")
    metadata_path = instance.instance_dir / "instance.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["icon"] = str(external)
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    instance = InstanceManager.load(instance.name)
    output = tmp_path / "legacy.mcwpack"

    PackageManager.export_instance(instance, output)

    with ZipFile(output) as archive:
        package = json.loads(archive.read("package.json"))
        exported_metadata = json.loads(archive.read("instance.json"))
        assert archive.read(".mcw/instance-icon.ico") == b"legacy-icon"
    assert package["instance_icon"] == ".mcw/instance-icon.ico"
    assert exported_metadata["icon"] == ".mcw/instance-icon.ico"
