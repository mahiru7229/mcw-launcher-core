from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile

from src.models.content.content_pack import ContentPackEntry
from src.models.instance.instance import Instance


class ContentPackRegistry:
    SCHEMA_VERSION = 1
    REGISTRY_RELATIVE_PATH = Path(".mcw") / "content-packs.json"

    @classmethod
    def path(cls, instance: Instance) -> Path:
        return Path(instance.instance_dir) / cls.REGISTRY_RELATIVE_PATH

    @classmethod
    def load(cls, instance: Instance) -> dict:
        path = cls.path(instance)
        if not path.is_file():
            return cls._empty()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return cls._empty()
        if not isinstance(payload, dict):
            return cls._empty()
        entries = payload.get("entries")
        if not isinstance(entries, list):
            entries = []
        return {"schemaVersion": cls.SCHEMA_VERSION, "entries": [item for item in entries if isinstance(item, dict)]}

    @classmethod
    def save(cls, instance: Instance, payload: dict) -> Path:
        path = cls.path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = {"schemaVersion": cls.SCHEMA_VERSION, "entries": list(payload.get("entries", []))}
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(normalized, output, ensure_ascii=False, indent=2)
                output.flush()
                os.fsync(output.fileno())
            Path(temp_name).replace(path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
        return path

    @classmethod
    def entries(cls, instance: Instance, content_type: str = "") -> list[ContentPackEntry]:
        normalized_type = str(content_type).strip().lower()
        output: list[ContentPackEntry] = []
        for raw in cls.load(instance).get("entries", []):
            entry = cls._parse_entry(raw)
            if entry is None or (normalized_type and entry.content_type != normalized_type):
                continue
            output.append(entry)
        output.sort(key=lambda item: (item.content_type, item.project_name.casefold(), item.file_name.casefold()))
        return output

    @classmethod
    def upsert(cls, instance: Instance, entry: ContentPackEntry) -> None:
        payload = cls.load(instance)
        entries = payload.setdefault("entries", [])
        replacement = cls._to_dict(entry)
        matched = False
        for index, raw in enumerate(entries):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("entryId") or "") == entry.entry_id:
                entries[index] = replacement
                matched = True
                break
        if not matched:
            entries.append(replacement)
        cls.save(instance, payload)

    @classmethod
    def remove(cls, instance: Instance, entry_id: str) -> ContentPackEntry | None:
        payload = cls.load(instance)
        normalized = str(entry_id).strip()
        removed: ContentPackEntry | None = None
        kept: list[dict] = []
        for raw in payload.get("entries", []):
            if not isinstance(raw, dict):
                continue
            if str(raw.get("entryId") or "") == normalized and removed is None:
                removed = cls._parse_entry(raw)
                continue
            kept.append(raw)
        payload["entries"] = kept
        cls.save(instance, payload)
        return removed

    @staticmethod
    def _empty() -> dict:
        return {"schemaVersion": ContentPackRegistry.SCHEMA_VERSION, "entries": []}

    @staticmethod
    def _parse_entry(raw: dict) -> ContentPackEntry | None:
        try:
            content_type = str(raw.get("contentType") or "").strip().lower()
            file_name = str(raw.get("fileName") or "").strip()
            entry_id = str(raw.get("entryId") or "").strip()
            if content_type not in {"resourcepack", "shader"} or not file_name or not entry_id:
                return None
            return ContentPackEntry(
                entry_id=entry_id,
                content_type=content_type,
                provider=str(raw.get("provider") or "local").strip().lower(),
                project_id=str(raw.get("projectId") or "").strip(),
                version_id=str(raw.get("versionId") or "").strip(),
                file_id=str(raw.get("fileId") or "").strip(),
                project_name=str(raw.get("projectName") or file_name).strip(),
                version_number=str(raw.get("versionNumber") or "").strip(),
                pack_format=int(raw["packFormat"]) if isinstance(raw.get("packFormat"), int) and int(raw["packFormat"]) > 0 else None,
                pack_description=str(raw.get("packDescription") or "").strip(),
                file_name=file_name,
                target_path=str(raw.get("targetPath") or "").strip(),
                sha1=str(raw.get("sha1") or "").strip().lower(),
                sha512=str(raw.get("sha512") or "").strip().lower(),
                size=max(0, int(raw.get("size") or 0)),
                source_url=str(raw.get("sourceUrl") or "").strip(),
                project_url=str(raw.get("projectUrl") or "").strip(),
                installed_at=str(raw.get("installedAt") or "").strip(),
                enabled=bool(raw.get("enabled", True)),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_dict(entry: ContentPackEntry) -> dict:
        return {
            "entryId": entry.entry_id,
            "contentType": entry.content_type,
            "provider": entry.provider,
            "projectId": entry.project_id,
            "versionId": entry.version_id,
            "fileId": entry.file_id,
            "projectName": entry.project_name,
            "versionNumber": entry.version_number,
            "packFormat": entry.pack_format,
            "packDescription": entry.pack_description,
            "fileName": entry.file_name,
            "targetPath": entry.target_path,
            "sha1": entry.sha1,
            "sha512": entry.sha512,
            "size": entry.size,
            "sourceUrl": entry.source_url,
            "projectUrl": entry.project_url,
            "installedAt": entry.installed_at,
            "enabled": entry.enabled,
        }
