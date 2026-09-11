from __future__ import annotations

import json

from src.core.fs.paths import Paths
from src.core.mod.mod_provider_alias_registry import ModProviderAliasRegistry


def test_verified_modrinth_alias_round_trip_and_forget(tmp_path, monkeypatch) -> None:
    path = tmp_path / "cache" / "mod-provider-aliases.json"
    monkeypatch.setattr(Paths, "mod_provider_alias_cache", lambda: path)

    ModProviderAliasRegistry.remember_modrinth("Cloth-Config2", "9s6osm5g", "cloth-config", "HpMb5wGb")

    entry = ModProviderAliasRegistry.get("cloth-config2")
    assert entry is not None
    assert entry["provider"] == "modrinth"
    assert entry["projectId"] == "9s6osm5g"
    assert entry["verifiedVersionId"] == "HpMb5wGb"
    assert json.loads(path.read_text(encoding="utf-8"))["schemaVersion"] == 1

    ModProviderAliasRegistry.forget("cloth-config2")
    assert ModProviderAliasRegistry.get("cloth-config2") is None


def test_alias_registry_ignores_untrusted_provider_entries(tmp_path, monkeypatch) -> None:
    path = tmp_path / "mod-provider-aliases.json"
    path.write_text(
        json.dumps({"schemaVersion": 1, "aliases": {"example": {"provider": "unknown", "projectId": "bad"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(Paths, "mod_provider_alias_cache", lambda: path)

    assert ModProviderAliasRegistry.get("example") is None
