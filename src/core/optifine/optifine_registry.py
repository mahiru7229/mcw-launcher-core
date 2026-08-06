from __future__ import annotations

from datetime import datetime, timezone
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance
from src.models.optifine.optifine_models import OptiFineState


class OptiFineRegistry:
    SCHEMA_VERSION = 1

    @staticmethod
    def empty() -> dict:
        return {"schemaVersion": OptiFineRegistry.SCHEMA_VERSION, "installed": False, "status": "not_installed"}

    @staticmethod
    def load(instance: Instance) -> dict:
        path = Paths.optifine_registry(instance)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return OptiFineRegistry.empty()
        return OptiFineRegistry.normalize(payload if isinstance(payload, dict) else {})

    @staticmethod
    def state(instance: Instance) -> OptiFineState:
        data = OptiFineRegistry.load(instance)
        return OptiFineState(
            installed=bool(data.get("installed", False)),
            minecraft_version=str(data.get("minecraftVersion") or ""),
            version_id=str(data.get("versionId") or ""),
            filename=str(data.get("fileName") or ""),
            mode=str(data.get("mode") or ""),
            managed=bool(data.get("managed", False)),
            sha256=str(data.get("sha256") or ""),
            size=int(data.get("size", 0) or 0),
            source_path=str(data.get("sourcePath") or ""),
            installed_path=str(data.get("installedPath") or ""),
            profile_path=str(data.get("profilePath") or ""),
            compatibility_state=str(data.get("compatibilityState") or "unknown"),
            status=str(data.get("status") or "not_installed"),
        )

    @staticmethod
    def save(instance: Instance, payload: dict) -> dict:
        path = Paths.optifine_registry(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = OptiFineRegistry.normalize(payload)
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return normalized

    @staticmethod
    def clear(instance: Instance) -> None:
        Paths.optifine_registry(instance).unlink(missing_ok=True)

    @staticmethod
    def normalize(payload: dict) -> dict:
        try:
            size = max(0, int(payload.get("size", 0) or 0))
        except (TypeError, ValueError):
            size = 0
        mode = str(payload.get("mode") or "").strip().casefold()
        if mode not in {"standalone", "forge_mod"}:
            mode = ""
        installed = bool(payload.get("installed", False) and mode)
        return {
            "schemaVersion": OptiFineRegistry.SCHEMA_VERSION,
            "installed": installed,
            "status": str(payload.get("status") or ("installed" if installed else "not_installed")),
            "minecraftVersion": str(payload.get("minecraftVersion") or "").strip(),
            "versionId": str(payload.get("versionId") or "").strip(),
            "fileName": str(payload.get("fileName") or "").strip(),
            "mode": mode,
            "managed": bool(payload.get("managed", installed)),
            "sha256": str(payload.get("sha256") or "").strip().casefold(),
            "sha1": str(payload.get("sha1") or "").strip().casefold(),
            "size": size,
            "sourcePath": str(payload.get("sourcePath") or "").strip(),
            "installedPath": str(payload.get("installedPath") or "").strip(),
            "profilePath": str(payload.get("profilePath") or "").strip(),
            "compatibilityState": str(payload.get("compatibilityState") or "unknown").strip().casefold(),
            "preview": bool(payload.get("preview", False)),
            "forgeVersion": str(payload.get("forgeVersion") or "").strip(),
            "officialPage": str(payload.get("officialPage") or "https://optifine.net/downloads").strip(),
        }
