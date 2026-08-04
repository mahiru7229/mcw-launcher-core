from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile

from src.models.instance.instance import Instance


class ContentLibraryPreferences:
    SCHEMA_VERSION = 1
    RELATIVE_PATH = Path(".mcw") / "content-library.json"

    @classmethod
    def path(cls, instance: Instance) -> Path:
        return Path(instance.instance_dir) / cls.RELATIVE_PATH

    @classmethod
    def load(cls, instance: Instance) -> dict[str, dict[str, bool]]:
        path = cls.path(instance)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError, TypeError):
            return {}
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), dict):
            return {}
        output: dict[str, dict[str, bool]] = {}
        for raw_id, raw in payload["items"].items():
            item_id = str(raw_id).strip()
            if not item_id or not isinstance(raw, dict):
                continue
            pinned = bool(raw.get("pinned", False))
            ignored = bool(raw.get("ignoredUpdate", False))
            if pinned or ignored:
                output[item_id] = {"pinned": pinned, "ignoredUpdate": ignored}
        return output

    @classmethod
    def save(cls, instance: Instance, items: dict[str, dict[str, bool]]) -> Path:
        path = cls.path(instance)
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized: dict[str, dict[str, bool]] = {}
        for raw_id, raw in items.items():
            item_id = str(raw_id).strip()
            if not item_id or not isinstance(raw, dict):
                continue
            pinned = bool(raw.get("pinned", False))
            ignored = bool(raw.get("ignoredUpdate", False))
            if pinned or ignored:
                normalized[item_id] = {"pinned": pinned, "ignoredUpdate": ignored}
        payload = {"schemaVersion": cls.SCHEMA_VERSION, "items": normalized}
        fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(payload, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            Path(temporary_name).replace(path)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        return path

    @classmethod
    def set_flags(cls, instance: Instance, item_ids: list[str] | tuple[str, ...] | set[str], *, pinned: bool | None = None, ignored_update: bool | None = None) -> tuple[str, ...]:
        normalized_ids = tuple(dict.fromkeys(str(item_id).strip() for item_id in item_ids if str(item_id).strip()))
        if not normalized_ids:
            return ()
        items = cls.load(instance)
        changed: list[str] = []
        for item_id in normalized_ids:
            current = dict(items.get(item_id, {}))
            before = dict(current)
            if pinned is not None:
                current["pinned"] = bool(pinned)
            if ignored_update is not None:
                current["ignoredUpdate"] = bool(ignored_update)
            if not bool(current.get("pinned", False)) and not bool(current.get("ignoredUpdate", False)):
                items.pop(item_id, None)
            else:
                items[item_id] = current
            if current != before:
                changed.append(item_id)
        if changed:
            cls.save(instance, items)
        return tuple(changed)

    @classmethod
    def prune(cls, instance: Instance, valid_item_ids: set[str]) -> None:
        items = cls.load(instance)
        retained = {item_id: value for item_id, value in items.items() if item_id in valid_item_ids}
        if retained != items:
            cls.save(instance, retained)
