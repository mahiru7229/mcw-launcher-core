from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class ModrinthRegistry:
    SCHEMA_VERSION = 2

    @staticmethod
    def load(instance: Instance) -> dict:
        path = Paths.modrinth_instance_registry(instance)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return ModrinthRegistry.empty()
        if not isinstance(data, dict):
            return ModrinthRegistry.empty()
        return ModrinthRegistry._normalize(data)

    @staticmethod
    def empty() -> dict:
        return {"schemaVersion": ModrinthRegistry.SCHEMA_VERSION, "mods": {}}

    @staticmethod
    def save(instance: Instance, data: dict) -> None:
        path = Paths.modrinth_instance_registry(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = ModrinthRegistry._normalize(data)
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def set_locked(instance: Instance, project_ids: list[str] | tuple[str, ...] | set[str], locked: bool) -> tuple[str, ...]:
        registry = ModrinthRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        changed: list[str] = []
        for project_id in project_ids:
            key = str(project_id).strip()
            entry = mods.get(key)
            if not key or not isinstance(entry, dict):
                continue
            entry["locked"] = bool(locked)
            changed.append(key)
        if changed:
            ModrinthRegistry.save(instance, registry)
        return tuple(changed)

    @staticmethod
    def remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]:
        names = {Path(str(filename)).name.casefold() for filename in filenames if str(filename).strip()}
        if not names:
            return ()
        registry = ModrinthRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        removed: list[str] = []
        for project_id, entry in list(mods.items()):
            if isinstance(entry, dict) and str(entry.get("fileName") or "").casefold() in names:
                mods.pop(project_id, None)
                removed.append(str(project_id))
        if removed:
            ModrinthRegistry.save(instance, registry)
        return tuple(removed)

    @staticmethod
    def entries_by_file(instance: Instance) -> dict[str, dict]:
        registry = ModrinthRegistry.load(instance)
        result: dict[str, dict] = {}
        for project_id, entry in registry.get("mods", {}).items():
            if not isinstance(entry, dict):
                continue
            filename = str(entry.get("fileName") or "").strip().casefold()
            if filename:
                result[filename] = {**entry, "projectId": str(entry.get("projectId") or project_id)}
        return result

    @staticmethod
    def safe_tracked_path(instance: Instance, filename: str) -> Path | None:
        directory = Paths.instance_mods_dir(instance).resolve()
        candidate = (directory / Path(filename).name).resolve()
        if candidate.parent != directory:
            return None
        return candidate

    @staticmethod
    def _normalize(data: dict) -> dict:
        mods_value = data.get("mods") if isinstance(data.get("mods"), dict) else {}
        mods: dict[str, dict] = {}
        for project_id, raw_entry in mods_value.items():
            if not isinstance(raw_entry, dict):
                continue
            key = str(raw_entry.get("projectId") or project_id).strip()
            if not key:
                continue
            entry = dict(raw_entry)
            entry["projectId"] = key
            entry["versionId"] = str(entry.get("versionId") or "").strip()
            entry["versionNumber"] = str(entry.get("versionNumber") or "Unknown").strip()
            entry["fileName"] = Path(str(entry.get("fileName") or "")).name
            entry["sha1"] = str(entry.get("sha1") or "").strip().lower()
            entry["sha512"] = str(entry.get("sha512") or "").strip().lower()
            try:
                entry["size"] = max(0, int(entry.get("size", 0) or 0))
            except (TypeError, ValueError):
                entry["size"] = 0
            entry["downloadUrls"] = list(dict.fromkeys(str(url).strip() for url in entry.get("downloadUrls", []) if str(url).strip())) if isinstance(entry.get("downloadUrls"), (list, tuple)) else []
            entry["pendingDownload"] = bool(entry.get("pendingDownload", False))
            entry["lastDownloadError"] = str(entry.get("lastDownloadError") or "").strip()
            entry["title"] = str(entry.get("title") or key).strip()
            entry["versionType"] = str(entry.get("versionType") or "release").strip().lower()
            entry["datePublished"] = str(entry.get("datePublished") or "").strip()
            entry["locked"] = bool(entry.get("locked", False))
            entry["source"] = "modrinth"
            mods[key] = entry
        normalized = {key: value for key, value in data.items() if key not in {"schemaVersion", "mods"}}
        normalized["schemaVersion"] = ModrinthRegistry.SCHEMA_VERSION
        normalized["mods"] = mods
        return normalized
