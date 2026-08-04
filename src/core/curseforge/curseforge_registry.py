from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class CurseForgeRegistry:
    SCHEMA_VERSION = 1

    @staticmethod
    def empty() -> dict:
        return {"schemaVersion": CurseForgeRegistry.SCHEMA_VERSION, "mods": {}}

    @staticmethod
    def load(instance: Instance) -> dict:
        path = Paths.curseforge_instance_registry(instance)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return CurseForgeRegistry.empty()
        return CurseForgeRegistry._normalize(data if isinstance(data, dict) else {})

    @staticmethod
    def save(instance: Instance, data: dict) -> None:
        path = Paths.curseforge_instance_registry(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = CurseForgeRegistry._normalize(data)
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def remove_by_filenames(instance: Instance, filenames: list[str] | tuple[str, ...] | set[str]) -> tuple[str, ...]:
        names = {Path(str(item)).name.casefold() for item in filenames if str(item).strip()}
        if not names:
            return ()
        registry = CurseForgeRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        removed: list[str] = []
        for project_id, entry in list(mods.items()):
            if isinstance(entry, dict) and str(entry.get("fileName") or "").casefold() in names:
                mods.pop(project_id, None)
                removed.append(str(project_id))
        if removed:
            CurseForgeRegistry.save(instance, registry)
        return tuple(removed)

    @staticmethod
    def safe_tracked_path(instance: Instance, filename: str) -> Path | None:
        root = Paths.instance_mods_dir(instance).resolve()
        candidate = (root / Path(filename).name).resolve()
        return candidate if candidate.parent == root else None

    @staticmethod
    def _normalize(data: dict) -> dict:
        raw_mods = data.get("mods") if isinstance(data.get("mods"), dict) else {}
        mods: dict[str, dict] = {}
        for project_id, raw in raw_mods.items():
            if not isinstance(raw, dict):
                continue
            try:
                key = str(int(raw.get("projectId") or project_id))
                file_id = int(raw.get("fileId") or 0)
            except (TypeError, ValueError):
                continue
            if file_id <= 0:
                continue
            item = dict(raw)
            item.update({
                "projectId": int(key),
                "fileId": file_id,
                "fileName": Path(str(item.get("fileName") or "")).name,
                "displayName": str(item.get("displayName") or item.get("fileName") or key).strip(),
                "sha1": str(item.get("sha1") or "").strip().lower(),
                "size": max(0, int(item.get("size", 0) or 0)),
                "downloadUrl": str(item.get("downloadUrl") or "").strip(),
                "releaseType": str(item.get("releaseType") or "release").strip().lower(),
                "pendingDownload": bool(item.get("pendingDownload", False)),
                "lastDownloadError": str(item.get("lastDownloadError") or "").strip(),
                "retryableDownload": bool(item.get("retryableDownload", True)),
                "acceptedUnverified": bool(item.get("acceptedUnverified", False)),
                "compatibilityWarning": str(item.get("compatibilityWarning") or "").strip(),
                "source": "curseforge",
            })
            mods[key] = item
        output = {key: value for key, value in data.items() if key not in {"schemaVersion", "mods"}}
        output["schemaVersion"] = CurseForgeRegistry.SCHEMA_VERSION
        output["mods"] = mods
        return output
