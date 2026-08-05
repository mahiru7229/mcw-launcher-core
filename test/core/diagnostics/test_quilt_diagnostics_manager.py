from pathlib import Path
from types import SimpleNamespace
import json
import zipfile

import pytest

from src.core.diagnostics.quilt_diagnostics_manager import QuiltDiagnosticsManager
from src.core.fs.paths import Paths
from src.core.lan.lan_agent_manager import LanAgentManager
from src.core.mod.mod_manager import ModManager
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path, loader: str = "quilt") -> Instance:
    root = tmp_path / "Quilt"
    root.mkdir()
    (root / "instance.json").write_text(json.dumps({"name": "Quilt", "token": "secret"}), encoding="utf-8")
    (root / "settings.json").write_text(json.dumps({"java_path": ""}), encoding="utf-8")
    return Instance(instance_id="quilt-id", name="Quilt", version_id="1.20.1", instance_dir=root, mod_loader=(loader, "0.28.0"))


def test_export_quilt_diagnostics_contains_profile_inventory_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    instance = make_instance(tmp_path)
    profile = tmp_path / "quilt-profile.json"
    profile.write_text(json.dumps({
        "id": "quilt-loader-0.28.0-1.20.1",
        "inheritsFrom": "1.20.1",
        "mainClass": "org.quiltmc.loader.impl.launch.knot.KnotClient",
        "libraries": [],
        "downloads": {},
        "assetIndex": {},
        "assets": "legacy",
        "arguments": {"game": [], "jvm": []},
        "javaVersion": {"majorVersion": 17},
        "quilt": {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "0.28.0"},
    }), encoding="utf-8")
    latest_log = Path(instance.instance_dir) / "logs" / "latest.log"
    latest_log.parent.mkdir()
    latest_log.write_text("Quilt started", encoding="utf-8")
    agent_log = Path(instance.instance_dir) / ".mcw" / "logs" / "mcw-lan-agent.log"
    agent_log.parent.mkdir(parents=True)
    agent_log.write_text("loader=quilt", encoding="utf-8")

    monkeypatch.setattr(Paths, "quilt_version_json", staticmethod(lambda game, loader: profile))
    monkeypatch.setattr(LanAgentManager, "log_path", classmethod(lambda cls, received: agent_log))
    monkeypatch.setattr(ModManager, "list_mods", staticmethod(lambda received: [SimpleNamespace(
        file_name="example.jar", enabled=True, mod_id="example", name="Example", version="1.0",
        loader="quilt", metadata_format="quilt.mod.json", dependencies=(), recommends=(), status="ready", error="",
    )]))

    output = QuiltDiagnosticsManager.export(instance, tmp_path / "diagnostics", "0.12.0-beta.3")

    assert output.suffix == ".zip"
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert {"summary.txt", "quilt/profile.json", "mods/inventory.json", "minecraft/latest.log", "lan/mcw-lan-agent.log"} <= names
        summary = archive.read("summary.txt").decode()
        assert "MCW Launcher Quilt Diagnostic Package" in summary
        assert "loader_version: 0.28.0" in summary
        inventory = json.loads(archive.read("mods/inventory.json"))
        assert inventory[0]["loader"] == "quilt"


def test_export_quilt_diagnostics_rejects_other_loaders(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, loader="fabric")

    with pytest.raises(RuntimeError, match="only for Quilt"):
        QuiltDiagnosticsManager.export(instance, tmp_path / "diagnostics.zip", "0.12.0-beta.3")
