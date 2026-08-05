import json
from pathlib import Path
import zipfile

from src.core.diagnostics.forge_diagnostics_manager import ForgeDiagnosticsManager
from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


def profile() -> dict:
    return {
        "id": "forge-1.20.1-47.4.21",
        "arguments": {"game": ["--fml.forgeVersion", "47.4.21"], "jvm": []},
        "libraries": [{"name": "net.minecraftforge:fmlloader:1.20.1-47.4.21"}],
        "downloads": {},
        "assetIndex": {},
        "assets": "1.20",
        "mainClass": "cpw.mods.bootstraplauncher.BootstrapLauncher",
        "javaVersion": {"majorVersion": 17},
        "forge": {"schemaVersion": 1, "gameVersion": "1.20.1", "loaderVersion": "47.4.21"},
    }


def test_export_builds_private_forge_diagnostics_zip(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Paths, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(Paths, "LOGS_ROOT", tmp_path / "logs")
    instance_dir = tmp_path / "instances" / "Forge Test"
    instance_dir.mkdir(parents=True)
    instance = Instance(
        instance_id="id",
        name="Forge Test",
        version_id="1.20.1",
        instance_dir=instance_dir,
        mod_loader=("forge", "47.4.21"),
    )
    (instance_dir / "instance.json").write_text(json.dumps({"id": "id", "name": "Forge Test", "token": "secret"}), encoding="utf-8")
    (instance_dir / "settings.json").write_text(json.dumps({"launch": {"max_memory": 4096}, "refresh_token": "secret"}), encoding="utf-8")
    (instance_dir / "logs").mkdir()
    (instance_dir / "logs" / "latest.log").write_text("Authorization: Bearer abc.def.ghi\nForge started", encoding="utf-8")
    profile_path = Paths.forge_version_json("1.20.1", "47.4.21")
    profile_path.write_text(json.dumps(profile()), encoding="utf-8")
    forge_log = Paths.forge_root() / "logs" / "forge-1.20.1-47.4.21.log"
    forge_log.parent.mkdir(parents=True, exist_ok=True)
    forge_log.write_text("installer ok", encoding="utf-8")

    output = ForgeDiagnosticsManager.export(instance, tmp_path / "diagnostics", launcher_version="0.6.0-beta.3")

    assert output.name == "diagnostics.zip"
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "summary.txt" in names
        assert "forge/profile.json" in names
        assert "mods/inventory.json" in names
        assert "minecraft/latest.log" in names
        assert not any("accounts" in name or "saves" in name for name in names)
        payload = "\n".join(archive.read(name).decode("utf-8") for name in names)
        assert "secret" not in payload
        assert "abc.def.ghi" not in payload
        assert "<redacted>" in payload
