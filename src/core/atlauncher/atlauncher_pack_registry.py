from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class ATLauncherPackRegistry:
    SCHEMA_VERSION = 1

    @staticmethod
    def load(instance: Instance | Path) -> dict:
        path = Paths.atlauncher_pack_registry(instance) if isinstance(instance, Instance) or getattr(instance, "instance_dir", None) is not None else Path(instance) / ".mcw" / "atlauncher-pack.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return ATLauncherPackRegistry._normalize(data if isinstance(data, dict) else {})

    @staticmethod
    def save(instance: Instance | Path, data: dict) -> None:
        path = Paths.atlauncher_pack_registry(instance) if isinstance(instance, Instance) or getattr(instance, "instance_dir", None) is not None else Path(instance) / ".mcw" / "atlauncher-pack.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = ATLauncherPackRegistry._normalize(dict(data))
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def is_managed(instance: Instance | Path) -> bool:
        return bool(ATLauncherPackRegistry.load(instance))

    @staticmethod
    def _normalize(data: dict) -> dict:
        managed: list[dict[str, object]] = []
        for raw in data.get("managedFiles", []) if isinstance(data.get("managedFiles"), list) else []:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or raw.get("fileName") or "").replace("\\", "/").strip().lstrip("/")
            pure = PurePosixPath(path)
            if not path or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts) or ":" in pure.parts[0]:
                continue
            filename = Path(str(raw.get("fileName") or pure.name)).name
            urls = raw.get("urls") if isinstance(raw.get("urls"), list) else []
            managed.append({
                "fileId": str(raw.get("fileId") or "").strip(),
                "fileName": filename,
                "name": str(raw.get("name") or filename).strip(),
                "path": pure.as_posix(),
                "sha1": str(raw.get("sha1") or "").strip().casefold(),
                "md5": str(raw.get("md5") or "").strip().casefold(),
                "size": max(0, ATLauncherPackRegistry._int(raw.get("size"))),
                "urls": list(dict.fromkeys(str(url).strip() for url in urls if str(url).strip())),
                "optional": bool(raw.get("optional", False)),
                "clientOnly": bool(raw.get("clientOnly", False)),
                "library": bool(raw.get("library", False)),
                "pendingDownload": bool(raw.get("pendingDownload", False)),
                "lastDownloadError": str(raw.get("lastDownloadError") or "").strip(),
                "provider": "atlauncher",
            })
        config = data.get("configBundle") if isinstance(data.get("configBundle"), dict) else None
        normalized_config = None
        if config:
            normalized_config = {
                "url": str(config.get("url") or "").strip(),
                "sha1": str(config.get("sha1") or "").strip().casefold(),
                "size": max(0, ATLauncherPackRegistry._int(config.get("size"))),
                "applied": bool(config.get("applied", False)),
                "pendingDownload": bool(config.get("pendingDownload", True)),
                "lastDownloadError": str(config.get("lastDownloadError") or "").strip(),
            }
        output = dict(data)
        output["schemaVersion"] = ATLauncherPackRegistry.SCHEMA_VERSION
        output["source"] = "atlauncher"
        output["packId"] = str(data.get("packId") or "").strip()
        output["safeName"] = str(data.get("safeName") or "").strip()
        output["versionId"] = str(data.get("versionId") or "").strip()
        output["versionName"] = str(data.get("versionName") or "").strip()
        output["managedFiles"] = sorted(managed, key=lambda item: str(item["path"]).casefold())
        output["configBundle"] = normalized_config
        output["unsupportedActions"] = [str(value).strip() for value in data.get("unsupportedActions", []) if str(value).strip()] if isinstance(data.get("unsupportedActions"), list) else []
        return output

    @staticmethod
    def _int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
