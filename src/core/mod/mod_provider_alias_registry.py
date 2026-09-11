from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from src.core.fs.paths import Paths


class ModProviderAliasRegistry:
    """Caches provider projects whose downloaded JARs proved a mod identity.

    Provider slugs and embedded mod IDs are independent namespaces.  An alias
    is therefore trusted only after MCW downloads a hash-verified provider file
    and reads the requested mod ID from that JAR.  The cache is disposable: a
    stale entry is revalidated before use and can always be rediscovered.
    """

    SCHEMA_VERSION = 1
    PROVIDERS = {"modrinth"}

    @staticmethod
    def empty() -> dict:
        return {"schemaVersion": ModProviderAliasRegistry.SCHEMA_VERSION, "aliases": {}}

    @staticmethod
    def load() -> dict:
        path = Paths.mod_provider_alias_cache()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return ModProviderAliasRegistry.empty()
        if not isinstance(payload, dict):
            return ModProviderAliasRegistry.empty()
        aliases = payload.get("aliases") if isinstance(payload.get("aliases"), dict) else {}
        normalized: dict[str, dict] = {}
        for raw_mod_id, raw_entry in aliases.items():
            mod_id = ModProviderAliasRegistry._mod_id(raw_mod_id)
            if not mod_id or not isinstance(raw_entry, dict):
                continue
            provider = str(raw_entry.get("provider") or "").strip().casefold()
            project_id = str(raw_entry.get("projectId") or "").strip()
            if provider not in ModProviderAliasRegistry.PROVIDERS or not project_id:
                continue
            normalized[mod_id] = {
                "modId": mod_id,
                "provider": provider,
                "projectId": project_id,
                "projectSlug": str(raw_entry.get("projectSlug") or "").strip(),
                "verifiedVersionId": str(raw_entry.get("verifiedVersionId") or "").strip(),
                "verifiedAt": str(raw_entry.get("verifiedAt") or "").strip(),
            }
        return {"schemaVersion": ModProviderAliasRegistry.SCHEMA_VERSION, "aliases": normalized}

    @staticmethod
    def get(mod_id: str, provider: str = "modrinth") -> dict | None:
        normalized_id = ModProviderAliasRegistry._mod_id(mod_id)
        normalized_provider = str(provider or "").strip().casefold()
        entry = ModProviderAliasRegistry.load().get("aliases", {}).get(normalized_id)
        if not isinstance(entry, dict) or entry.get("provider") != normalized_provider:
            return None
        return dict(entry)

    @staticmethod
    def remember_modrinth(mod_id: str, project_id: str, project_slug: str = "", version_id: str = "") -> None:
        normalized_id = ModProviderAliasRegistry._mod_id(mod_id)
        normalized_project = str(project_id or "").strip()
        if not normalized_id or not normalized_project:
            return
        payload = ModProviderAliasRegistry.load()
        payload.setdefault("aliases", {})[normalized_id] = {
            "modId": normalized_id,
            "provider": "modrinth",
            "projectId": normalized_project,
            "projectSlug": str(project_slug or "").strip(),
            "verifiedVersionId": str(version_id or "").strip(),
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
        }
        ModProviderAliasRegistry._save(payload)

    @staticmethod
    def forget(mod_id: str, provider: str = "modrinth") -> None:
        normalized_id = ModProviderAliasRegistry._mod_id(mod_id)
        normalized_provider = str(provider or "").strip().casefold()
        payload = ModProviderAliasRegistry.load()
        entry = payload.get("aliases", {}).get(normalized_id)
        if not isinstance(entry, dict) or entry.get("provider") != normalized_provider:
            return
        payload["aliases"].pop(normalized_id, None)
        ModProviderAliasRegistry._save(payload)

    @staticmethod
    def _save(payload: dict) -> None:
        path = Paths.mod_provider_alias_cache()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _mod_id(value: object) -> str:
        return str(value or "").strip().casefold()
