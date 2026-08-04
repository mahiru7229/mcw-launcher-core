from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
import json
import re

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class ModProvenanceRegistry:
    """Unified source identity for installed and manifest-managed mod files.

    Provider-specific registries remain authoritative for their own install and
    update workflows. This registry normalizes those records by destination file
    so the UI and future MCWPack exporter can recover provenance consistently.
    """

    SCHEMA_VERSION = 1
    _MODRINTH_CDN_PATTERN = re.compile(r"^/data/([^/]+)/versions/([^/]+)/([^/]+)$", re.IGNORECASE)
    _PROVIDERS = {"modrinth", "curseforge", "ftb", "local", "manual", "unknown"}

    @staticmethod
    def empty() -> dict:
        return {"schemaVersion": ModProvenanceRegistry.SCHEMA_VERSION, "mods": {}}

    @staticmethod
    def load(instance: Instance) -> dict:
        path = Paths.mod_provenance_registry(instance)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return ModProvenanceRegistry.empty()
        return ModProvenanceRegistry._normalize(payload if isinstance(payload, dict) else {})

    @staticmethod
    def save(instance: Instance, data: dict) -> None:
        path = Paths.mod_provenance_registry(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = ModProvenanceRegistry._normalize(data)
        payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def synchronize(instance: Instance) -> dict[str, dict]:
        current = ModProvenanceRegistry.load(instance)
        merged: dict[str, dict] = {}
        for key, value in current.get("mods", {}).items():
            if isinstance(value, dict) and bool(value.get("explicit", False)):
                retained = dict(value)
                retained["_priority"] = 15
                merged[str(key).casefold()] = retained

        def merge(entry: dict, priority: int) -> None:
            normalized = ModProvenanceRegistry._normalize_entry(entry)
            if normalized is None:
                return
            key = normalized["fileName"].casefold()
            previous = merged.get(key)
            previous_priority = int(previous.get("_priority", 0)) if isinstance(previous, dict) else -1
            if previous is None or priority >= previous_priority:
                normalized["_priority"] = priority
                merged[key] = normalized

        # Pack manifests are available before first launch, so source identity is
        # retained even while the actual JAR is still pending download.
        ModProvenanceRegistry._merge_modrinth_pack(instance, merge)
        ModProvenanceRegistry._merge_curseforge_pack(instance, merge)
        ModProvenanceRegistry._merge_ftb_pack(instance, merge)

        # Directly installed mods are more specific than a pack-level record.
        from src.core.modrinth.modrinth_registry import ModrinthRegistry
        from src.core.curseforge.curseforge_registry import CurseForgeRegistry

        for project_id, raw in ModrinthRegistry.load(instance).get("mods", {}).items():
            if not isinstance(raw, dict):
                continue
            merge({
                "fileName": raw.get("fileName"),
                "provider": "modrinth",
                "projectId": raw.get("projectId") or project_id,
                "versionId": raw.get("versionId"),
                "versionNumber": raw.get("versionNumber"),
                "sha1": raw.get("sha1"),
                "sha512": raw.get("sha512"),
                "size": raw.get("size"),
                "downloadUrls": raw.get("downloadUrls", []),
                "managedByModpack": False,
            }, 30)

        for project_id, raw in CurseForgeRegistry.load(instance).get("mods", {}).items():
            if not isinstance(raw, dict):
                continue
            merge({
                "fileName": raw.get("fileName"),
                "provider": "curseforge",
                "projectId": raw.get("projectId") or project_id,
                "fileId": raw.get("fileId"),
                "versionNumber": raw.get("displayName"),
                "sha1": raw.get("sha1"),
                "size": raw.get("size"),
                "downloadUrls": [raw.get("downloadUrl")] if raw.get("downloadUrl") else [],
                "managedByModpack": False,
            }, 30)

        for entry in merged.values():
            entry.pop("_priority", None)
        output = {"schemaVersion": ModProvenanceRegistry.SCHEMA_VERSION, "mods": merged}
        normalized = ModProvenanceRegistry._normalize(output)
        if normalized != current:
            ModProvenanceRegistry.save(instance, normalized)
        return normalized["mods"]

    @staticmethod
    def entries_by_file(instance: Instance, synchronize: bool = True) -> dict[str, dict]:
        data = ModProvenanceRegistry.synchronize(instance) if synchronize else ModProvenanceRegistry.load(instance).get("mods", {})
        return {str(key).casefold(): dict(value) for key, value in data.items() if isinstance(value, dict)}

    @staticmethod
    def entry_for_file(instance: Instance, filename: str) -> dict | None:
        key = ModProvenanceRegistry._base_filename(filename).casefold()
        return ModProvenanceRegistry.entries_by_file(instance).get(key)

    @staticmethod
    def record_many(instance: Instance, entries: list[dict] | tuple[dict, ...]) -> None:
        data = ModProvenanceRegistry.load(instance)
        mods = data.setdefault("mods", {})
        changed = False
        for raw in entries:
            candidate = dict(raw) if isinstance(raw, dict) else {}
            candidate["explicit"] = True
            normalized = ModProvenanceRegistry._normalize_entry(candidate)
            if normalized is None:
                continue
            key = normalized["fileName"].casefold()
            if mods.get(key) != normalized:
                mods[key] = normalized
                changed = True
        if changed:
            ModProvenanceRegistry.save(instance, data)

    @staticmethod
    def remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]:
        keys = {ModProvenanceRegistry._base_filename(value).casefold() for value in filenames if str(value).strip()}
        if not keys:
            return ()
        data = ModProvenanceRegistry.load(instance)
        mods = data.setdefault("mods", {})
        removed: list[str] = []
        for key in list(mods):
            if key.casefold() in keys:
                removed.append(str(mods[key].get("fileName") or key))
                mods.pop(key, None)
        if removed:
            ModProvenanceRegistry.save(instance, data)
        return tuple(removed)

    @staticmethod
    def _merge_modrinth_pack(instance: Instance, merge) -> None:
        from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry

        pack = ModrinthPackRegistry.load(instance)
        pack_project_id = str(pack.get("projectId") or "").strip()
        pack_version_id = str(pack.get("versionId") or "").strip()
        for raw in pack.get("managedFiles", []):
            if not isinstance(raw, dict) or not ModProvenanceRegistry._is_mod_path(raw.get("path")):
                continue
            downloads = [str(value).strip() for value in raw.get("downloads", []) if str(value).strip()] if isinstance(raw.get("downloads"), list) else []
            project_id = str(raw.get("projectId") or "").strip()
            version_id = str(raw.get("versionId") or "").strip()
            remote_name = ""
            for url in downloads:
                parsed = ModProvenanceRegistry._modrinth_identity_from_url(url)
                if parsed is not None:
                    project_id = project_id or parsed[0]
                    version_id = version_id or parsed[1]
                    remote_name = remote_name or parsed[2]
                    break
            merge({
                "fileName": raw.get("fileName") or remote_name or PurePosixPath(str(raw.get("path") or "")).name,
                "path": raw.get("path"),
                "provider": "modrinth",
                "projectId": project_id,
                "versionId": version_id,
                "sha1": raw.get("sha1"),
                "sha512": raw.get("sha512"),
                "size": raw.get("size"),
                "downloadUrls": downloads,
                "managedByModpack": True,
                "packProvider": "modrinth",
                "packProjectId": pack_project_id,
                "packVersionId": pack_version_id,
            }, 20)

    @staticmethod
    def _merge_curseforge_pack(instance: Instance, merge) -> None:
        from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry

        pack = CurseForgePackRegistry.load(instance)
        pack_project_id = str(pack.get("projectId") or "").strip()
        pack_version_id = str(pack.get("fileId") or pack.get("versionId") or "").strip()
        for raw in pack.get("managedFiles", []):
            if not isinstance(raw, dict) or not ModProvenanceRegistry._is_mod_path(raw.get("path")):
                continue
            merge({
                "fileName": raw.get("fileName") or PurePosixPath(str(raw.get("path") or "")).name,
                "path": raw.get("path"),
                "provider": raw.get("provider") or "curseforge",
                "projectId": raw.get("projectId"),
                "fileId": raw.get("fileId"),
                "versionNumber": raw.get("displayName"),
                "sha1": raw.get("sha1"),
                "size": raw.get("size"),
                "downloadUrls": [raw.get("downloadUrl")] if raw.get("downloadUrl") else [],
                "managedByModpack": True,
                "packProvider": "curseforge",
                "packProjectId": pack_project_id,
                "packVersionId": pack_version_id,
            }, 20)

    @staticmethod
    def _merge_ftb_pack(instance: Instance, merge) -> None:
        from src.core.ftb.ftb_pack_registry import FTBPackRegistry

        pack = FTBPackRegistry.load(instance)
        pack_project_id = str(pack.get("projectId") or "").strip()
        pack_version_id = str(pack.get("versionId") or "").strip()
        for raw in pack.get("managedFiles", []):
            if not isinstance(raw, dict) or not ModProvenanceRegistry._is_mod_path(raw.get("path")):
                continue
            merge({
                "fileName": raw.get("fileName") or PurePosixPath(str(raw.get("path") or "")).name,
                "path": raw.get("path"),
                "provider": raw.get("provider") or "ftb",
                "fileId": raw.get("fileId"),
                "sha1": raw.get("sha1"),
                "size": raw.get("size"),
                "downloadUrls": raw.get("urls", []),
                "managedByModpack": True,
                "packProvider": "ftb",
                "packProjectId": pack_project_id,
                "packVersionId": pack_version_id,
            }, 20)

    @staticmethod
    def _normalize(data: dict) -> dict:
        raw_mods = data.get("mods") if isinstance(data.get("mods"), dict) else {}
        mods: dict[str, dict] = {}
        for raw in raw_mods.values():
            normalized = ModProvenanceRegistry._normalize_entry(raw)
            if normalized is None:
                continue
            mods[normalized["fileName"].casefold()] = normalized
        return {"schemaVersion": ModProvenanceRegistry.SCHEMA_VERSION, "mods": mods}

    @staticmethod
    def _normalize_entry(raw: object) -> dict | None:
        if not isinstance(raw, dict):
            return None
        filename = ModProvenanceRegistry._base_filename(raw.get("fileName") or PurePosixPath(str(raw.get("path") or "")).name)
        if not filename or not filename.casefold().endswith(".jar"):
            return None
        provider = str(raw.get("provider") or "unknown").strip().casefold()
        if provider not in ModProvenanceRegistry._PROVIDERS:
            provider = "unknown"
        try:
            size = max(0, int(raw.get("size", 0) or 0))
        except (TypeError, ValueError):
            size = 0
        urls = raw.get("downloadUrls", [])
        if not isinstance(urls, (list, tuple)):
            urls = []
        return {
            "fileName": filename,
            "path": ModProvenanceRegistry._safe_mod_path(raw.get("path"), filename),
            "provider": provider,
            "projectId": str(raw.get("projectId") or "").strip(),
            "versionId": str(raw.get("versionId") or "").strip(),
            "fileId": str(raw.get("fileId") or "").strip(),
            "versionNumber": str(raw.get("versionNumber") or "").strip(),
            "sha1": str(raw.get("sha1") or "").strip().casefold(),
            "sha512": str(raw.get("sha512") or "").strip().casefold(),
            "size": size,
            "downloadUrls": list(dict.fromkeys(str(url).strip() for url in urls if str(url).strip())),
            "sources": ModProvenanceRegistry._normalize_sources(raw.get("sources")),
            "projectUrl": str(raw.get("projectUrl") or "").strip(),
            "licenseId": str(raw.get("licenseId") or "").strip(),
            "licenseName": str(raw.get("licenseName") or "").strip(),
            "licenseUrl": str(raw.get("licenseUrl") or "").strip(),
            "redistributionAllowed": bool(raw.get("redistributionAllowed", False)),
            "managedByModpack": bool(raw.get("managedByModpack", False)),
            "packProvider": str(raw.get("packProvider") or "").strip().casefold(),
            "packProjectId": str(raw.get("packProjectId") or "").strip(),
            "packVersionId": str(raw.get("packVersionId") or "").strip(),
            "explicit": bool(raw.get("explicit", False)),
        }

    @staticmethod
    def _normalize_sources(value: object) -> list[dict]:
        if not isinstance(value, (list, tuple)):
            return []
        output: list[dict] = []
        seen: set[tuple] = set()
        for index, raw in enumerate(value, start=1):
            if not isinstance(raw, dict):
                continue
            provider = str(raw.get("provider") or "direct").strip().casefold() or "direct"
            urls = raw.get("urls") if isinstance(raw.get("urls"), (list, tuple)) else []
            normalized = {
                "provider": provider,
                "projectId": str(raw.get("projectId") or "").strip(),
                "versionId": str(raw.get("versionId") or "").strip(),
                "fileId": str(raw.get("fileId") or "").strip(),
                "urls": list(dict.fromkeys(str(url).strip() for url in urls if str(url).strip())),
                "priority": max(1, int(raw.get("priority", index * 10) or index * 10)),
            }
            identity = (normalized["provider"], normalized["projectId"], normalized["versionId"], normalized["fileId"], tuple(normalized["urls"]))
            if identity in seen or not any(identity[1:]):
                continue
            seen.add(identity)
            output.append(normalized)
        output.sort(key=lambda source: (source["priority"], source["provider"]))
        return output

    @staticmethod
    def _is_mod_path(value: object) -> bool:
        normalized = str(value or "").replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        lowered = path.name.casefold()
        return len(path.parts) >= 2 and path.parts[0].casefold() == "mods" and (lowered.endswith(".jar") or lowered.endswith(".jar.disabled"))

    @staticmethod
    def _safe_mod_path(value: object, filename: str) -> str:
        fallback = f"mods/{filename}"
        normalized = str(value or fallback).replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return fallback
        allowed_names = {filename.casefold(), f"{filename}.disabled".casefold()}
        if len(path.parts) < 2 or path.parts[0].casefold() != "mods" or path.name.casefold() not in allowed_names:
            return fallback
        return path.as_posix()

    @staticmethod
    def _base_filename(value: object) -> str:
        filename = Path(str(value or "")).name
        if filename.casefold().endswith(".disabled"):
            filename = filename[:-len(".disabled")]
        return filename

    @staticmethod
    def _modrinth_identity_from_url(url: str) -> tuple[str, str, str] | None:
        try:
            parsed = urlparse(str(url).strip())
        except ValueError:
            return None
        if parsed.scheme.casefold() != "https" or parsed.hostname not in {"cdn.modrinth.com", "cdn-raw.modrinth.com"}:
            return None
        match = ModProvenanceRegistry._MODRINTH_CDN_PATTERN.fullmatch(parsed.path)
        if match is None:
            return None
        return tuple(unquote(value) for value in match.groups())
