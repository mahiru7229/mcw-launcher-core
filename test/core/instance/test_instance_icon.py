from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager


@pytest.fixture
def instance_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "instances"
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", root)
    return root


def test_set_icon_copies_file_inside_instance_and_updates_schema(instance_root: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Icon Test", SimpleNamespace(id="1.20.1"))
    source = tmp_path / "custom.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\ncustom-icon")

    updated = InstanceManager.set_icon(instance.name, source)

    assert updated.icon == ".mcw/instance-icon.png"
    stored = updated.instance_dir / updated.icon
    assert stored.read_bytes() == source.read_bytes()
    metadata = json.loads((updated.instance_dir / "instance.json").read_text(encoding="utf-8"))
    assert metadata["icon"] == ".mcw/instance-icon.png"
    assert metadata["metadata_version"] == 3


def test_changing_icon_removes_previous_managed_icon(instance_root: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Icon Replace", SimpleNamespace(id="1.20.1"))
    first = tmp_path / "first.png"
    second = tmp_path / "second.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    InstanceManager.set_icon(instance.name, first)
    updated = InstanceManager.set_icon(instance.name, second)

    assert updated.icon == ".mcw/instance-icon.jpg"
    assert not (updated.instance_dir / ".mcw" / "instance-icon.png").exists()
    assert (updated.instance_dir / updated.icon).read_bytes() == b"second"


def test_reset_icon_removes_managed_file(instance_root: Path, tmp_path: Path) -> None:
    instance = InstanceManager.create("Icon Reset", SimpleNamespace(id="1.20.1"))
    source = tmp_path / "custom.webp"
    source.write_bytes(b"custom")
    InstanceManager.set_icon(instance.name, source)

    updated = InstanceManager.reset_icon(instance.name)

    assert updated.icon == InstanceManager.DEFAULT_ICON
    assert not list((updated.instance_dir / ".mcw").glob("instance-icon.*"))


@pytest.mark.parametrize("filename", ["icon.txt", "icon.svg"])
def test_set_icon_rejects_unsupported_formats(instance_root: Path, tmp_path: Path, filename: str) -> None:
    instance = InstanceManager.create("Icon Invalid", SimpleNamespace(id="1.20.1"))
    source = tmp_path / filename
    source.write_text("invalid", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Unsupported instance icon format"):
        InstanceManager.set_icon(instance.name, source)
