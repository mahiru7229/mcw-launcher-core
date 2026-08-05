import json
from pathlib import Path

from src.core.instance.settings_manager import SettingsManager, default_instance_settings
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path) -> Instance:
    instance_dir = tmp_path / "instance"
    instance_dir.mkdir()
    return Instance(instance_id="id", name="Settings", version_id="1.20.1", instance_dir=instance_dir, mod_loader=("fabric", "0.16.0"))


def test_legacy_settings_without_failure_choice_inherit_launcher_defaults(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "java": {"path": "", "min_memory": 1024, "max_memory": 2048, "arguments": []},
        "window": {"width": 1280, "height": 720, "fullscreen": False},
        "launch": {"game_arguments": [], "offline_multiplayer_enabled": False},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.modrinth_failure_policy == "inherit"
    assert settings.curseforge_failure_policy == "inherit"
    assert settings.forge_preflight_failure_policy == "inherit"


def test_failure_policies_are_saved_per_instance(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    settings = SettingsManager.load(instance)
    settings.modrinth_failure_policy = "allow"
    settings.curseforge_failure_policy = "block"
    settings.forge_preflight_failure_policy = "allow"

    SettingsManager.save(instance, settings)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["launch"]["modrinth_failure_policy"] == "allow"
    assert saved["launch"]["curseforge_failure_policy"] == "block"
    assert saved["launch"]["forge_preflight_failure_policy"] == "allow"
    reloaded = SettingsManager.load(instance)
    assert reloaded.modrinth_failure_policy == "allow"
    assert reloaded.curseforge_failure_policy == "block"
    assert reloaded.forge_preflight_failure_policy == "allow"


def test_legacy_modrinth_boolean_is_migrated_for_both_sources(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "launch": {"block_launch_on_modrinth_failure": False},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.modrinth_failure_policy == "allow"
    assert settings.curseforge_failure_policy == "allow"


def test_invalid_setting_types_fall_back_without_crashing(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "java": {"path": None, "min_memory": "invalid", "max_memory": -1, "arguments": "not-a-list"},
        "window": {"width": "bad", "height": 0, "fullscreen": "false"},
        "launch": {"game_arguments": None, "offline_multiplayer_enabled": "yes", "block_launch_on_modrinth_failure": "off"},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.min_memory == 1024
    assert settings.max_memory == 2048
    assert settings.width == 1280
    assert settings.height == 720
    assert settings.jvm_arguments == []
    assert settings.game_arguments == []
    assert settings.fullscreen is False
    assert settings.offline_multiplayer_enabled is True
    assert settings.lan_auth_mode == "private_offline"
    assert settings.lan_connection_provider == "manual"
    assert settings.modrinth_failure_policy == "allow"
    assert settings.curseforge_failure_policy == "allow"


def test_broken_settings_are_backed_up_and_recreated(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    settings_path = instance.instance_dir / "settings.json"
    settings_path.write_text("{broken-json", encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.min_memory == 1024
    assert settings_path.is_file()
    assert (instance.instance_dir / "settings.json.broken").read_text(encoding="utf-8") == "{broken-json"
    launch = json.loads(settings_path.read_text(encoding="utf-8"))["launch"]
    assert launch["modrinth_failure_policy"] == "inherit"
    assert launch["curseforge_failure_policy"] == "inherit"


def test_save_uses_atomic_temporary_file(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    settings = SettingsManager.load(instance)
    settings.max_memory = 4096

    SettingsManager.save(instance, settings)

    assert json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))["java"]["max_memory"] == 4096
    assert not (instance.instance_dir / "settings.json.tmp").exists()


def test_loaded_memory_is_clamped_to_physical_ram(tmp_path: Path, monkeypatch) -> None:
    from src.core.system.memory import SystemMemory

    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 4096))
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "java": {"path": "", "min_memory": 8192, "max_memory": 16384, "arguments": []},
        "window": {"width": 1280, "height": 720, "fullscreen": False},
        "launch": {"game_arguments": [], "offline_multiplayer_enabled": False},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.min_memory == 4096
    assert settings.max_memory == 4096


def test_saved_memory_is_clamped_to_physical_ram(tmp_path: Path, monkeypatch) -> None:
    from src.core.system.memory import SystemMemory

    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 4096))
    instance = make_instance(tmp_path)
    settings = SettingsManager.load(instance)
    settings.min_memory = 6144
    settings.max_memory = 8192

    SettingsManager.save(instance, settings)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["java"]["min_memory"] == 4096
    assert saved["java"]["max_memory"] == 4096


def test_lan_hosting_profile_is_saved_and_legacy_flag_is_retired(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    settings = SettingsManager.load(instance)
    settings.offline_multiplayer_enabled = True
    settings.lan_auth_mode = "private_offline"
    settings.lan_connection_provider = "e4mc"

    SettingsManager.save(instance, settings)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert saved["launch"]["offline_multiplayer_enabled"] is False
    assert saved["launch"]["lan_auth_mode"] == "private_offline"
    assert saved["launch"]["lan_connection_provider"] == "e4mc"
    reloaded = SettingsManager.load(instance)
    assert reloaded.lan_auth_mode == "private_offline"
    assert reloaded.lan_connection_provider == "e4mc"


def test_legacy_friends_auth_mode_is_migrated_when_loaded_and_saved(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "java": {"path": "", "min_memory": 1024, "max_memory": 2048, "arguments": []},
        "window": {"width": 1280, "height": 720, "fullscreen": False},
        "launch": {"game_arguments": [], "lan_auth_mode": "friends", "lan_connection_provider": "manual"},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)
    SettingsManager.save(instance, settings)

    saved = json.loads((instance.instance_dir / "settings.json").read_text(encoding="utf-8"))
    assert settings.lan_auth_mode == "private_offline"
    assert saved["launch"]["lan_auth_mode"] == "private_offline"


def test_legacy_modrinth_boolean_does_not_change_forge_preflight_policy(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)
    (instance.instance_dir / "settings.json").write_text(json.dumps({
        "launch": {"block_launch_on_modrinth_failure": False},
    }), encoding="utf-8")

    settings = SettingsManager.load(instance)

    assert settings.forge_preflight_failure_policy == "inherit"


def test_public_dict_codec_returns_canonical_independent_data(monkeypatch) -> None:
    from src.core.system.memory import SystemMemory

    monkeypatch.setattr(SystemMemory, "total_physical_memory_mb", classmethod(lambda cls: 4096))
    source = {
        "java": {"path": None, "min_memory": 8192, "max_memory": 16384, "arguments": ["-Xmx4G"]},
        "window": {"width": "1920", "height": 0, "fullscreen": "yes"},
        "launch": {"game_arguments": ["--demo"], "lan_auth_mode": "friends"},
    }

    normalized = SettingsManager.normalize_dict(source)
    source["java"]["arguments"].append("-Dchanged=true")

    assert normalized["java"]["min_memory"] == 4096
    assert normalized["java"]["max_memory"] == 4096
    assert normalized["java"]["arguments"] == ["-Xmx4G"]
    assert normalized["window"]["width"] == 1920
    assert normalized["window"]["height"] == 720
    assert normalized["window"]["fullscreen"] is True
    assert normalized["launch"]["lan_auth_mode"] == "private_offline"


def test_default_instance_settings_is_available_without_class_factory() -> None:
    first = default_instance_settings()
    second = default_instance_settings()

    first["java"]["path"] = "C:/changed/javaw.exe"

    assert second["java"]["path"] == ""
    assert SettingsManager.default_dict() == second
