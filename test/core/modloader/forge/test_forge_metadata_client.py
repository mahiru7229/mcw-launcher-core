from src.core.modloader.forge.forge_metadata_client import ForgeMetadataClient


def test_parse_and_filter_forge_versions(monkeypatch) -> None:
    raw = b"""<metadata><versioning><versions>
    <version>1.20.1-47.2.0</version>
    <version>1.20.1-47.3.0</version>
    <version>1.19.2-43.4.0</version>
    </versions></versioning></metadata>"""
    versions = ForgeMetadataClient._parse_metadata(raw)
    monkeypatch.setattr(ForgeMetadataClient, "_all_versions", staticmethod(lambda force_refresh=False: versions))

    result = ForgeMetadataClient.list_versions("1.20.1")

    assert [item.forge_version for item in result] == ["47.3.0", "47.2.0"]
    assert ForgeMetadataClient.recommended_version("1.20.1") == "47.3.0"


def test_installer_url_uses_official_maven_layout() -> None:
    assert ForgeMetadataClient.installer_url("1.20.1", "47.3.0").endswith(
        "/1.20.1-47.3.0/forge-1.20.1-47.3.0-installer.jar"
    )


def test_installer_url_strips_duplicate_game_and_forge_prefixes() -> None:
    expected = "https://maven.minecraftforge.net/net/minecraftforge/forge/1.12.2-14.23.5.2858/forge-1.12.2-14.23.5.2858-installer.jar"
    assert ForgeMetadataClient.installer_url("1.12.2", "1.12.2-14.23.5.2858") == expected
    assert ForgeMetadataClient.installer_url("1.12.2", "forge-14.23.5.2858") == expected
    assert ForgeMetadataClient.installer_url("1.12.2", "forge-1.12.2-14.23.5.2858") == expected
