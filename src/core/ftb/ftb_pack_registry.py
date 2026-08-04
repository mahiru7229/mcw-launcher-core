from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class FTBPackRegistry:
    SCHEMA_VERSION = 2

    @staticmethod
    def load(instance: Instance | Path) -> dict:
        path = Paths.ftb_pack_registry(instance) if isinstance(instance, Instance) or getattr(instance, "instance_dir", None) is not None else Path(instance) / ".mcw" / "ftb-pack.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return FTBPackRegistry._normalize(data if isinstance(data, dict) else {})

    @staticmethod
    def save(instance: Instance | Path, data: dict) -> None:
        path = Paths.ftb_pack_registry(instance) if isinstance(instance, Instance) or getattr(instance, "instance_dir", None) is not None else Path(instance) / ".mcw" / "ftb-pack.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = FTBPackRegistry._normalize(data)
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temporary = path.with_suffix(path.suffix + ".part")
        temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def safe_relative_path(value: str, fallback_filename: str) -> str:
        filename = Path(str(fallback_filename or "download.bin")).name or "download.bin"
        normalized = str(value or filename).replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return filename
        if not path.parts or ":" in path.parts[0]:
            return filename
        return path.as_posix()

    @staticmethod
    def _normalize(data: dict) -> dict:
        managed: list[dict] = []
        for raw in data.get("managedFiles", []):
            if not isinstance(raw, dict):
                continue
            file_id = FTBPackRegistry._int(raw.get("fileId"))
            filename = Path(str(raw.get("fileName") or "")).name
            if file_id <= 0 or not filename:
                continue
            path = FTBPackRegistry.safe_relative_path(str(raw.get("path") or filename), filename)
            managed.append({
                "fileId": file_id,
                "fileName": filename,
                "path": path,
                "sha1": str(raw.get("sha1") or "").strip().casefold(),
                "size": max(0, FTBPackRegistry._int(raw.get("size"))),
                "urls": list(dict.fromkeys(str(url).strip() for url in raw.get("urls", []) if str(url).strip())) if isinstance(raw.get("urls"), list) else [],
                "optional": bool(raw.get("optional", False)),
                "clientOnly": bool(raw.get("clientOnly", False)),
                "fileType": str(raw.get("fileType") or "").strip(),
                "pendingDownload": bool(raw.get("pendingDownload", False)),
                "lastDownloadError": str(raw.get("lastDownloadError") or "").strip(),
                "provider": "ftb",
            })
        output = dict(data)
        output["schemaVersion"] = FTBPackRegistry.SCHEMA_VERSION
        output["source"] = "ftb"
        output["managedFiles"] = sorted(managed, key=lambda item: str(item["path"]).casefold())
        return output

    @staticmethod
    def _int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
