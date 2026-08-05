from pathlib import Path
import json

from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path) -> Instance:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    return Instance(instance_id="id", name="Test", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def test_migrates_schema_one_and_preserves_mod_entries(tmp_path):
    instance = make_instance(tmp_path)
    path = instance.instance_dir / ".mcw" / "modrinth.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"schemaVersion": 1, "mods": {"project": {"versionId": "v1", "versionNumber": "1.0", "fileName": "example.jar", "title": "Example"}}}), encoding="utf-8")

    data = ModrinthRegistry.load(instance)

    assert data["schemaVersion"] == 2
    assert data["mods"]["project"]["locked"] is False
    assert data["mods"]["project"]["source"] == "modrinth"


def test_sets_version_lock_atomically(tmp_path):
    instance = make_instance(tmp_path)
    ModrinthRegistry.save(instance, {"mods": {"project": {"projectId": "project", "versionId": "v1", "fileName": "example.jar"}}})

    changed = ModrinthRegistry.set_locked(instance, ["project"], True)

    assert changed == ("project",)
    assert ModrinthRegistry.load(instance)["mods"]["project"]["locked"] is True
