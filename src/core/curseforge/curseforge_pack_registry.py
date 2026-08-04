from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import json

from src.core.fs.paths import Paths
from src.models.instance.instance import Instance


class CurseForgePackRegistry:
    SCHEMA_VERSION = 2

    @staticmethod
    def load(instance: Instance | Path) -> dict:
        path = Paths.curseforge_pack_registry(instance) if isinstance(instance, Instance) else Path(instance) / ".mcw" / "curseforge-pack.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return CurseForgePackRegistry._normalize(data if isinstance(data, dict) else {})

    @staticmethod
    def save(instance: Instance | Path, data: dict) -> None:
        path = Paths.curseforge_pack_registry(instance) if isinstance(instance, Instance) else Path(instance) / ".mcw" / "curseforge-pack.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = CurseForgePackRegistry._normalize(data)
        normalized["updatedAt"] = datetime.now(timezone.utc).isoformat()
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def safe_relative_path(value: str, fallback_filename: str) -> str:
        filename = Path(str(fallback_filename or "download.bin")).name or "download.bin"
        fallback = f"mods/{filename}"
        normalized = str(value or fallback).replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            return fallback
        if not path.parts or ":" in path.parts[0]:
            return fallback
        return path.as_posix()

    @staticmethod
    def managed_path(instance: Instance, value: str, fallback_filename: str) -> tuple[Path, str]:
        relative = CurseForgePackRegistry.safe_relative_path(value, fallback_filename)
        root = Path(instance.instance_dir).resolve()
        target = root.joinpath(*PurePosixPath(relative).parts).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise RuntimeError("The managed CurseForge path escapes the instance folder.") from error
        return target, relative

    @staticmethod
    def _normalize(data: dict) -> dict:
        managed: list[dict] = []
        for raw in data.get("managedFiles", []):
            if not isinstance(raw, dict):
                continue
            try:
                project_id = int(raw.get("projectId") or 0)
                file_id = int(raw.get("fileId") or 0)
            except (TypeError, ValueError):
                continue
            filename = Path(str(raw.get("fileName") or "")).name
            if project_id <= 0 or file_id <= 0 or not filename:
                continue
            safe_path = CurseForgePackRegistry.safe_relative_path(str(raw.get("path") or ""), filename)
            managed.append({
                "projectId": project_id,
                "fileId": file_id,
                "fileName": filename,
                "path": safe_path,
                "sha1": str(raw.get("sha1") or "").strip().lower(),
                "size": max(0, int(raw.get("size", 0) or 0)),
                "downloadUrl": str(raw.get("downloadUrl") or "").strip(),
                "required": bool(raw.get("required", True)),
                "displayName": str(raw.get("displayName") or filename).strip(),
                "pendingDownload": bool(raw.get("pendingDownload", False)),
                "lastDownloadError": str(raw.get("lastDownloadError") or "").strip(),
                "retryableDownload": bool(raw.get("retryableDownload", True)),
                "acceptedUnverified": bool(raw.get("acceptedUnverified", False)),
                "compatibilityWarning": str(raw.get("compatibilityWarning") or "").strip(),
                "manualImport": bool(raw.get("manualImport", False)),
                "resolvePathFromProvider": bool(raw.get("resolvePathFromProvider", False)),
                "provider": "curseforge",
            })
        output = dict(data)
        output["schemaVersion"] = CurseForgePackRegistry.SCHEMA_VERSION
        output["managedFiles"] = managed
        output["source"] = "curseforge"
        return output
