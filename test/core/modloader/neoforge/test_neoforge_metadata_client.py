from src.core.modloader.neoforge.neoforge_metadata_client import NeoForgeMetadataClient


def test_lists_legacy_1201_versions_from_neoforged_forge_artifact(monkeypatch) -> None:
    legacy = ("1.20.1-47.1.105", "1.20.1-47.1.106", "1.20.2-48.0.0",)
    monkeypatch.setattr(NeoForgeMetadataClient, "_artifact_versions", staticmethod(lambda artifact, force_refresh=False: legacy))

    versions = NeoForgeMetadataClient.list_versions("1.20.1")

    assert [item.neoforge_version for item in versions] == ["47.1.106", "47.1.105"]
    assert all(item.artifact == "forge" for item in versions)
    assert versions[0].resolved_coordinate_version == "1.20.1-47.1.106"


def test_lists_modern_versions_by_minecraft_line(monkeypatch) -> None:
    modern = ("20.4.237", "21.0.167", "21.1.200", "26.1.0.1-beta", "26.1.1",)
    monkeypatch.setattr(NeoForgeMetadataClient, "_artifact_versions", staticmethod(lambda artifact, force_refresh=False: modern))

    assert [item.neoforge_version for item in NeoForgeMetadataClient.list_versions("1.20.4")] == ["20.4.237"]
    assert [item.neoforge_version for item in NeoForgeMetadataClient.list_versions("1.21.1")] == ["21.1.200"]
    assert [item.neoforge_version for item in NeoForgeMetadataClient.list_versions("26.1")] == ["26.1.1", "26.1.0.1-beta"]


def test_installer_urls_use_correct_neoforged_artifact() -> None:
    legacy = NeoForgeMetadataClient.installer_url("1.20.1", "47.1.106")
    modern = NeoForgeMetadataClient.installer_url("1.21.1", "21.1.200")

    assert legacy.endswith("/net/neoforged/forge/1.20.1-47.1.106/forge-1.20.1-47.1.106-installer.jar")
    assert modern.endswith("/net/neoforged/neoforge/21.1.200/neoforge-21.1.200-installer.jar")
