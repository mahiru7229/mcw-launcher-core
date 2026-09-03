from types import SimpleNamespace

import pytest

from src.core.config.managed_content_policy import ManagedContentPolicy


def launcher_settings(modrinth: str = "block", curseforge: str = "block", forge_preflight: str = "block") -> dict:
    return {
        "managed_content": {
            "modrinth_failure_policy": modrinth,
            "curseforge_failure_policy": curseforge,
            "forge_preflight_failure_policy": forge_preflight,
        }
    }


def test_instance_policy_overrides_launcher_default() -> None:
    settings = SimpleNamespace(modrinth_failure_policy="allow", curseforge_failure_policy="block")

    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings("block", "allow"), "modrinth") is False
    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings("allow", "allow"), "curseforge") is True


def test_inherit_uses_source_specific_launcher_default() -> None:
    settings = SimpleNamespace(modrinth_failure_policy="inherit", curseforge_failure_policy="inherit")

    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings("block", "allow"), "modrinth") is True
    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings("block", "allow"), "curseforge") is False


def test_legacy_boolean_is_supported_for_both_sources() -> None:
    settings = SimpleNamespace(block_launch_on_modrinth_failure=False)

    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings(), "modrinth") is False
    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings(), "curseforge") is False


def test_invalid_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        ManagedContentPolicy.resolve(SimpleNamespace(), launcher_settings(), "unknown")


def test_forge_preflight_instance_policy_overrides_launcher_default() -> None:
    settings = SimpleNamespace(forge_preflight_failure_policy="allow")

    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings(forge_preflight="block"), "forge_preflight") is False


def test_forge_preflight_inherit_uses_launcher_default() -> None:
    settings = SimpleNamespace(forge_preflight_failure_policy="inherit")

    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings(forge_preflight="allow"), "forge_preflight") is False
    assert ManagedContentPolicy.blocks_launch(settings, launcher_settings(forge_preflight="block"), "forge_preflight") is True
