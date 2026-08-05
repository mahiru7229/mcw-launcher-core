from pathlib import Path

import pytest

from src.core.lan.lan_agent_manager import LanAgentInstallResult, LanAgentManager
from src.core.lan.lan_hosting_manager import LanHostingManager
from src.core.mod.mod_manager import ModManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_mod_installer import ModrinthModInstaller
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.models.instance.instance import Instance
from src.models.modrinth.install_result import ModrinthModInstallResult
from src.models.modrinth.version import ModrinthFile, ModrinthVersion


def make_instance(tmp_path: Path, loader: str = "fabric") -> Instance:
    instance_dir = tmp_path / loader
    (instance_dir / "mods").mkdir(parents=True)
    return Instance(instance_id=loader, name=loader.title(), version_id="1.20.1", instance_dir=instance_dir, mod_loader=(loader, "test"))


def make_version(slug: str, loader: str) -> ModrinthVersion:
    return ModrinthVersion(
        version_id=f"{slug}-version",
        project_id=f"{slug}-project",
        name="1.0",
        version_number="1.0",
        version_type="release",
        game_versions=("1.20.1",),
        loaders=(loader,),
        files=(ModrinthFile(url="https://example.invalid/mod.jar", filename=f"{slug}.jar", sha1="a", sha512="b", size=1, primary=True),),
    )


def test_plan_separates_agent_authentication_from_connection(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)

    manual_private = LanHostingManager.plan(instance, "private_offline", "manual")
    microsoft_e4mc = LanHostingManager.plan(instance, "microsoft_only", "e4mc")
    private_e4mc = LanHostingManager.plan(instance, "private_offline", "e4mc")

    assert manual_private.components == ()
    assert [component.project_slug for component in microsoft_e4mc.components] == ["e4mc"]
    assert [component.project_slug for component in private_e4mc.components] == ["e4mc"]


def test_legacy_friends_profile_migrates_to_private_offline(tmp_path: Path) -> None:
    instance = make_instance(tmp_path)

    plan = LanHostingManager.plan(instance, "friends", "manual")

    assert plan.auth_mode == "private_offline"
    assert plan.components == ()


def test_private_manual_profile_does_not_require_a_mod_loader(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "vanilla")

    plan = LanHostingManager.plan(instance, "private_offline", "manual")

    assert plan.components == ()


def test_tunnel_provider_requires_supported_mod_loader(tmp_path: Path) -> None:
    instance = make_instance(tmp_path, "vanilla")

    with pytest.raises(RuntimeError, match="tunnel provider requires a Fabric, Quilt, Forge, or NeoForge"):
        LanHostingManager.plan(instance, "private_offline", "e4mc")


def test_prepare_installs_agent_and_release_connection_component(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path, "forge")
    registry = {"schemaVersion": 2, "mods": {}}
    selected: list[tuple[str, str, str, tuple[str, ...]]] = []
    agent_path = tmp_path / "mcw-lan-agent.jar"

    def select_version(project_id: str, game_version: str, loader: str, version_types: tuple[str, ...]):
        selected.append((project_id, game_version, loader, version_types))
        return make_version(project_id, loader)

    def install(_instance, version_id: str, install_dependencies: bool, allowed_version_types: tuple[str, ...], reporter=None):
        slug = version_id.removesuffix("-version")
        project_id = f"{slug}-project"
        registry["mods"][project_id] = {
            "projectId": project_id,
            "versionId": version_id,
            "versionNumber": "1.0",
            "fileName": f"{slug}.jar",
            "title": "e4mc",
        }
        return ModrinthModInstallResult(installed_projects=("e4mc",), installed_files=(f"{slug}.jar",))

    monkeypatch.setattr(LanAgentManager, "install", classmethod(lambda cls: LanAgentInstallResult(agent_path, True)))
    monkeypatch.setattr(ModrinthClient, "select_version", staticmethod(select_version))
    monkeypatch.setattr(ModrinthModInstaller, "install", staticmethod(install))
    monkeypatch.setattr(ModrinthRegistry, "load", staticmethod(lambda _instance: registry))
    monkeypatch.setattr(ModrinthRegistry, "save", staticmethod(lambda _instance, _data: None))
    monkeypatch.setattr(LanHostingManager, "_entry_matches_installed_file", staticmethod(lambda *_args: False))
    monkeypatch.setattr(LanHostingManager, "_disable_unused_managed_components", staticmethod(lambda *_args: ()))

    result = LanHostingManager.prepare(instance, "private_offline", "e4mc")

    assert selected == [("e4mc", "1.20.1", "forge", ("release",))]
    assert result.installed_projects == ("MCW LAN Agent", "e4mc")
    assert str(agent_path) in result.installed_files
    assert registry["mods"]["e4mc-project"]["managedBy"] == LanHostingManager.MANAGED_BY
    assert registry["mods"]["e4mc-project"]["lanHostingRole"] == LanHostingManager.ROLE_CONNECTION


def test_disable_unused_managed_components_removes_previous_auth_bridge(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    old_file = instance.instance_dir / "mods" / "mcwifipnp.jar"
    old_file.write_bytes(b"old")
    registry = {
        "schemaVersion": 2,
        "mods": {
            "old-project": {
                "projectId": "old-project",
                "fileName": "mcwifipnp.jar",
                "title": "LAN World Plug-n-Play",
                "managedBy": LanHostingManager.MANAGED_BY,
                "lanHostingRole": LanHostingManager.ROLE_AUTH_BRIDGE,
                "lanHostingProjectSlug": "mcwifipnp",
            },
        },
    }
    disabled: list[tuple[list[Path], bool]] = []

    monkeypatch.setattr(ModrinthRegistry, "load", staticmethod(lambda _instance: registry))
    monkeypatch.setattr(ModManager, "set_enabled", staticmethod(lambda _instance, paths, enabled: disabled.append((list(paths), enabled))))

    result = LanHostingManager._disable_unused_managed_components(instance, set())

    assert result == ("LAN World Plug-n-Play",)
    assert disabled == [([old_file], False)]


def test_disable_legacy_auth_bridges_keeps_connection_component(tmp_path: Path, monkeypatch) -> None:
    instance = make_instance(tmp_path)
    auth_file = instance.instance_dir / "mods" / "mcwifipnp.jar"
    connection_file = instance.instance_dir / "mods" / "e4mc.jar"
    auth_file.write_bytes(b"auth")
    connection_file.write_bytes(b"connection")
    registry = {
        "schemaVersion": 2,
        "mods": {
            "auth": {
                "fileName": auth_file.name,
                "title": "LAN World Plug-n-Play",
                "managedBy": LanHostingManager.MANAGED_BY,
                "lanHostingRole": LanHostingManager.ROLE_AUTH_BRIDGE,
            },
            "connection": {
                "fileName": connection_file.name,
                "title": "e4mc",
                "managedBy": LanHostingManager.MANAGED_BY,
                "lanHostingRole": LanHostingManager.ROLE_CONNECTION,
            },
        },
    }
    disabled: list[Path] = []

    monkeypatch.setattr(ModrinthRegistry, "load", staticmethod(lambda _instance: registry))
    monkeypatch.setattr(ModManager, "set_enabled", staticmethod(lambda _instance, paths, enabled: disabled.extend(paths) if not enabled else None))

    result = LanHostingManager.disable_legacy_auth_bridges(instance)

    assert result == ("LAN World Plug-n-Play",)
    assert disabled == [auth_file]
