from types import SimpleNamespace

from src.core.minecraft.version_manager import VersionManager
from src.core.modloader.fabric.fabric_version_manager import FabricVersionManager
from src.core.modloader.forge.forge_version_manager import ForgeVersionManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modloader.neoforge.neoforge_version_manager import NeoForgeVersionManager
from src.core.modloader.quilt.quilt_version_manager import QuiltVersionManager


def test_loads_vanilla_version(monkeypatch):
    expected = object()
    monkeypatch.setattr(VersionManager, "load", lambda version_id: expected)
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("vanilla", "-1"))

    assert ModLoaderManager.load(instance) is expected


def test_loads_fabric_version(monkeypatch):
    expected = object()
    monkeypatch.setattr(FabricVersionManager, "load", lambda game_version, loader_version, reporter=None: expected)
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("fabric", "0.19.3"))

    assert ModLoaderManager.load(instance) is expected


def test_resolve_fabric_auto_uses_recommended_loader(monkeypatch):
    monkeypatch.setattr(FabricVersionManager, "recommended_loader_version", lambda game_version: "0.19.3")

    assert ModLoaderManager.resolve("1.21.1", "fabric", "auto") == ("fabric", "0.19.3")


def test_resolve_fabric_keeps_explicit_loader_version(monkeypatch):
    def unexpected_call(game_version):
        raise AssertionError("Explicit loader versions must not query the recommended version.")

    monkeypatch.setattr(FabricVersionManager, "recommended_loader_version", unexpected_call)

    assert ModLoaderManager.resolve("1.21.1", "fabric", "0.18.6") == ("fabric", "0.18.6")


def test_resolve_vanilla_normalizes_version():
    assert ModLoaderManager.resolve("1.21.1", "vanilla", "auto") == ("vanilla", "-1")


def test_resolve_fabric_legacy_missing_version_uses_recommended_loader(monkeypatch):
    monkeypatch.setattr(FabricVersionManager, "recommended_loader_version", lambda game_version: "0.19.3")

    assert ModLoaderManager.resolve("1.21.1", "fabric", "-1") == ("fabric", "0.19.3")


def test_repairs_fabric_instance(monkeypatch):
    expected = object()
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("fabric", "0.19.3"))
    base_version = object()
    monkeypatch.setattr(VersionManager, "load", lambda version_id: base_version)
    monkeypatch.setattr(FabricVersionManager, "repair", lambda version, loader_version, reporter=None: expected)

    assert ModLoaderManager.repair(instance) is expected


def test_repair_rejects_vanilla_instance():
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("vanilla", "-1"))

    import pytest

    with pytest.raises(RuntimeError, match="Only Fabric, Quilt, Forge, or NeoForge"):
        ModLoaderManager.repair(instance)



def test_loads_forge_version(monkeypatch):
    expected = object()
    monkeypatch.setattr(ForgeVersionManager, "load", lambda game_version, loader_version, reporter=None: expected)
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("forge", "47.3.0"))

    assert ModLoaderManager.load(instance) is expected


def test_resolve_forge_auto_uses_recommended_loader(monkeypatch):
    monkeypatch.setattr(ForgeVersionManager, "recommended_loader_version", lambda game_version: "47.3.0")

    assert ModLoaderManager.resolve("1.20.1", "forge", "auto") == ("forge", "47.3.0")


def test_repairs_forge_instance(monkeypatch):
    expected = object()
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("forge", "47.3.0"))
    base_version = object()
    monkeypatch.setattr(VersionManager, "load", lambda version_id: base_version)
    monkeypatch.setattr(ForgeVersionManager, "repair", lambda version, loader_version, reporter=None: expected)

    assert ModLoaderManager.repair(instance) is expected


def test_loads_neoforge_version(monkeypatch):
    expected = object()
    monkeypatch.setattr(NeoForgeVersionManager, "load", lambda game_version, loader_version, reporter=None: expected)
    instance = SimpleNamespace(version_id="1.21.1", mod_loader=("neoforge", "21.1.200"))

    assert ModLoaderManager.load(instance) is expected


def test_resolve_neoforge_auto_uses_recommended_loader(monkeypatch):
    monkeypatch.setattr(NeoForgeVersionManager, "recommended_loader_version", lambda game_version: "21.1.200")

    assert ModLoaderManager.resolve("1.21.1", "neoforge", "auto") == ("neoforge", "21.1.200")


def test_repairs_neoforge_instance(monkeypatch):
    expected = object()
    instance = SimpleNamespace(version_id="1.21.1", mod_loader=("neoforge", "21.1.200"))
    base_version = object()
    monkeypatch.setattr(VersionManager, "load", lambda version_id: base_version)
    monkeypatch.setattr(NeoForgeVersionManager, "repair", lambda version, loader_version, reporter=None: expected)

    assert ModLoaderManager.repair(instance) is expected


def test_loads_quilt_version(monkeypatch):
    expected = object()
    monkeypatch.setattr(QuiltVersionManager, "load", lambda game_version, loader_version, reporter=None: expected)
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("quilt", "0.27.1"))

    assert ModLoaderManager.load(instance) is expected


def test_resolve_quilt_auto_uses_recommended_loader(monkeypatch):
    monkeypatch.setattr(QuiltVersionManager, "recommended_loader_version", lambda game_version: "0.27.1")

    assert ModLoaderManager.resolve("1.20.1", "quilt", "auto") == ("quilt", "0.27.1")


def test_repairs_quilt_instance(monkeypatch):
    expected = object()
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("quilt", "0.27.1"))
    base_version = object()
    monkeypatch.setattr(VersionManager, "load", lambda version_id: base_version)
    monkeypatch.setattr(QuiltVersionManager, "repair", lambda version, loader_version, reporter=None: expected)

    assert ModLoaderManager.repair(instance) is expected


def test_forwards_preferred_java_to_forge_load(monkeypatch):
    expected = object()
    captured = {}

    def load(game_version, loader_version, reporter=None, preferred_java_path=None):
        captured["path"] = preferred_java_path
        return expected

    monkeypatch.setattr(ForgeVersionManager, "load", load)
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("forge", "47.3.0"))

    assert ModLoaderManager.load(instance, preferred_java_path="C:/Java/custom/javaw.exe") is expected
    assert captured["path"] == "C:/Java/custom/javaw.exe"


def test_forwards_preferred_java_to_forge_prepare(monkeypatch):
    expected = object()
    captured = {}

    def install(version, loader_version, reporter=None, force_refresh=False, preferred_java_path=None):
        captured["path"] = preferred_java_path
        return expected

    monkeypatch.setattr(ForgeVersionManager, "install", install)

    assert ModLoaderManager.prepare(object(), "forge", "47.3.0", preferred_java_path="C:/Java/custom/javaw.exe") is expected
    assert captured["path"] == "C:/Java/custom/javaw.exe"


def test_forwards_preferred_java_to_forge_repair(monkeypatch):
    expected = object()
    captured = {}
    instance = SimpleNamespace(version_id="1.20.1", mod_loader=("forge", "47.3.0"))
    monkeypatch.setattr(VersionManager, "load", lambda version_id: object())

    def repair(version, loader_version, reporter=None, preferred_java_path=None):
        captured["path"] = preferred_java_path
        return expected

    monkeypatch.setattr(ForgeVersionManager, "repair", repair)

    assert ModLoaderManager.repair(instance, preferred_java_path="C:/Java/custom/javaw.exe") is expected
    assert captured["path"] == "C:/Java/custom/javaw.exe"
