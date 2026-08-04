from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path, PurePosixPath

from src.core.content.content_library_preferences import ContentLibraryPreferences
from src.core.content.content_pack_manager import ContentPackManager
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.mod.mod_provenance_registry import ModProvenanceRegistry
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.models.content.installed_content import InstalledContentItem, InstalledContentLibrary
from src.models.instance.instance import Instance


class InstalledContentLibraryManager:
    MOD = "mod"
    RESOURCE_PACK = ContentPackManager.RESOURCE_PACK
    SHADER_PACK = ContentPackManager.SHADER_PACK
    MODPACK = "modpack"
    SUPPORTED_TYPES = frozenset({MOD, RESOURCE_PACK, SHADER_PACK, MODPACK})

    @classmethod
    def scan(cls, instance: Instance) -> InstalledContentLibrary:
        preferences = ContentLibraryPreferences.load(instance)
        items: list[InstalledContentItem] = []
        items.extend(cls._mod_items(instance))
        items.extend(cls._content_pack_items(instance))
        items.extend(cls._modpack_items(instance))

        decorated: list[InstalledContentItem] = []
        for item in items:
            flags = preferences.get(item.item_id, {})
            decorated.append(replace(item, pinned=bool(flags.get("pinned", False)), ignored_update=bool(flags.get("ignoredUpdate", False))))
        decorated.sort(key=cls._sort_key)
        ContentLibraryPreferences.prune(instance, {item.item_id for item in decorated})
        return InstalledContentLibrary(instance_name=instance.name, items=tuple(decorated))

    @classmethod
    def set_enabled(cls, instance: Instance, item_ids: list[str] | tuple[str, ...], enabled: bool) -> tuple[str, ...]:
        library = cls.scan(instance)
        selected = [item for item in library.items if item.item_id in set(item_ids)]
        changed: list[str] = []
        for item in selected:
            if not item.toggleable or item.status in {"pending", "missing"}:
                continue
            if item.content_type == cls.MOD:
                path = cls._safe_instance_path(instance, item.target_path)
                ModManager.set_enabled(instance, [path], bool(enabled))
            elif item.content_type in {cls.RESOURCE_PACK, cls.SHADER_PACK}:
                ContentPackManager.set_enabled(instance, cls._entry_id_from_item(item), bool(enabled))
            else:
                continue
            changed.append(item.item_id)
        return tuple(changed)

    @classmethod
    def remove(cls, instance: Instance, item_ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        library = cls.scan(instance)
        selected = [item for item in library.items if item.item_id in set(item_ids)]
        removed: list[str] = []
        for item in selected:
            if not item.removable:
                continue
            if item.content_type == cls.MOD:
                path = cls._safe_instance_path(instance, item.target_path)
                ModManager.remove_mods(instance, [path])
                ModrinthRegistry.remove_by_filenames(instance, [item.file_name])
                CurseForgeRegistry.remove_by_filenames(instance, [item.file_name])
            elif item.content_type in {cls.RESOURCE_PACK, cls.SHADER_PACK}:
                ContentPackManager.remove(instance, cls._entry_id_from_item(item))
            else:
                continue
            removed.append(item.item_id)
        if removed:
            ContentLibraryPreferences.prune(instance, {item.item_id for item in cls.scan(instance).items})
        return tuple(removed)

    @staticmethod
    def set_pinned(instance: Instance, item_ids: list[str] | tuple[str, ...], pinned: bool) -> tuple[str, ...]:
        return ContentLibraryPreferences.set_flags(instance, item_ids, pinned=bool(pinned))

    @staticmethod
    def set_ignored_update(instance: Instance, item_ids: list[str] | tuple[str, ...], ignored: bool) -> tuple[str, ...]:
        return ContentLibraryPreferences.set_flags(instance, item_ids, ignored_update=bool(ignored))

    @classmethod
    def destination_folder(cls, instance: Instance, content_type: str) -> Path:
        kind = str(content_type).strip().casefold()
        if kind == cls.MOD:
            return ModManager.mods_dir(instance)
        if kind in {cls.RESOURCE_PACK, cls.SHADER_PACK}:
            return ContentPackManager.destination_dir(instance, kind)
        if kind == cls.MODPACK:
            return Path(instance.instance_dir)
        raise RuntimeError(f"Unsupported content type: {content_type}")

    @classmethod
    def _mod_items(cls, instance: Instance) -> list[InstalledContentItem]:
        provenance = ModProvenanceRegistry.entries_by_file(instance)
        actual = ModManager.list_mods(instance)
        output: list[InstalledContentItem] = []
        consumed: set[str] = set()

        for mod in actual:
            key = mod.file_name.casefold()
            consumed.add(key)
            source = provenance.get(key, {})
            provider = cls._provider(source.get("provider") if source else mod.source)
            project_id = str(source.get("projectId") or mod.source_project_id or "").strip()
            version_id = str(source.get("versionId") or mod.source_version_id or "").strip()
            file_id = str(source.get("fileId") or mod.source_file_id or "").strip()
            target_path = cls._relative_to_instance(instance, mod.path)
            try:
                actual_size = max(0, int(mod.path.stat().st_size))
            except OSError:
                actual_size = max(0, cls._int(source.get("size")))
            status = "disabled" if not mod.enabled else "ready"
            if mod.error or str(mod.status).casefold() not in {"ready", "enabled", "disabled"}:
                status = "broken"
            managed = bool(source.get("managedByModpack", mod.managed_by_modpack))
            output.append(InstalledContentItem(
                item_id=cls._item_id(cls.MOD, provider, project_id, mod.file_name, str(source.get("sha512") or "")),
                content_type=cls.MOD,
                name=mod.name or Path(mod.file_name).stem,
                version=mod.version or str(source.get("versionNumber") or ""),
                provider=provider,
                project_id=project_id,
                version_id=version_id,
                file_id=file_id,
                file_name=mod.file_name,
                target_path=target_path,
                enabled=mod.enabled,
                managed_by_modpack=managed,
                source_pack_provider=cls._provider(source.get("packProvider") or mod.source_pack_provider) if managed else "",
                size=actual_size,
                sha1=str(source.get("sha1") or "").strip().casefold(),
                sha512=str(source.get("sha512") or "").strip().casefold(),
                project_url=cls._project_url(provider, project_id, cls.MOD),
                status=status,
                toggleable=True,
                removable=not managed,
            ))

        for key, source in provenance.items():
            if key in consumed or not isinstance(source, dict):
                continue
            file_name = Path(str(source.get("fileName") or key)).name
            if not file_name:
                continue
            provider = cls._provider(source.get("provider"))
            project_id = str(source.get("projectId") or "").strip()
            version_id = str(source.get("versionId") or "").strip()
            file_id = str(source.get("fileId") or "").strip()
            managed = bool(source.get("managedByModpack", False))
            raw_path = str(source.get("path") or f"mods/{file_name}")
            target_path = cls._safe_relative(raw_path, f"mods/{file_name}")
            target = cls._safe_instance_path(instance, target_path)
            status = "pending" if managed else "missing"
            if target.is_file():
                status = "ready"
            output.append(InstalledContentItem(
                item_id=cls._item_id(cls.MOD, provider, project_id, file_name, str(source.get("sha512") or "")),
                content_type=cls.MOD,
                name=str(source.get("title") or source.get("displayName") or Path(file_name).stem).strip(),
                version=str(source.get("versionNumber") or "").strip(),
                provider=provider,
                project_id=project_id,
                version_id=version_id,
                file_id=file_id,
                file_name=file_name,
                target_path=target_path,
                enabled=True,
                managed_by_modpack=managed,
                source_pack_provider=cls._provider(source.get("packProvider")) if managed else "",
                size=max(0, cls._int(source.get("size"))),
                sha1=str(source.get("sha1") or "").strip().casefold(),
                sha512=str(source.get("sha512") or "").strip().casefold(),
                project_url=cls._project_url(provider, project_id, cls.MOD),
                status=status,
                toggleable=target.is_file(),
                removable=False if managed else target.is_file(),
            ))
        return output

    @classmethod
    def _content_pack_items(cls, instance: Instance) -> list[InstalledContentItem]:
        output: list[InstalledContentItem] = []
        for entry in ContentPackManager.list_entries(instance):
            status = "ready" if entry.enabled else "disabled"
            target = cls._safe_instance_path(instance, entry.target_path)
            if not target.is_file():
                status = "missing"
            item = InstalledContentItem(
                item_id=f"content-pack:{entry.entry_id}",
                content_type=entry.content_type,
                name=entry.project_name or Path(entry.file_name).stem,
                version=entry.version_number,
                provider=cls._provider(entry.provider),
                project_id=entry.project_id,
                version_id=entry.version_id,
                file_id=entry.file_id,
                file_name=entry.file_name,
                target_path=entry.target_path,
                enabled=entry.enabled,
                managed_by_modpack=False,
                source_pack_provider="",
                size=max(0, int(entry.size)),
                sha1=entry.sha1,
                sha512=entry.sha512,
                project_url=entry.project_url,
                status=status,
                toggleable=status != "missing",
                removable=True,
            )
            output.append(item)
        return output

    @classmethod
    def _modpack_items(cls, instance: Instance) -> list[InstalledContentItem]:
        output: list[InstalledContentItem] = []
        registries = (
            ("modrinth", ModrinthPackRegistry.load(instance)),
            ("curseforge", CurseForgePackRegistry.load(instance)),
            ("ftb", FTBPackRegistry.load(instance)),
        )
        for provider, data in registries:
            if not isinstance(data, dict) or not data:
                continue
            project_id = str(data.get("projectId") or "").strip()
            version_id = str(data.get("versionId") or data.get("fileId") or "").strip()
            if not project_id and not version_id:
                continue
            managed_files = [raw for raw in data.get("managedFiles", []) if isinstance(raw, dict)] if isinstance(data.get("managedFiles"), list) else []
            pending = 0
            total_size = 0
            for raw in managed_files:
                total_size += max(0, cls._int(raw.get("size")))
                file_name = Path(str(raw.get("fileName") or "")).name
                raw_path = str(raw.get("path") or file_name)
                relative = cls._safe_relative(raw_path, f"mods/{file_name}" if file_name else "mods/pending.jar")
                if bool(raw.get("pendingDownload", False)) or not cls._safe_instance_path(instance, relative).is_file():
                    pending += 1
            status = "pending" if pending else "ready"
            name = str(data.get("name") or f"{provider.title()} modpack").strip()
            version = str(data.get("versionNumber") or data.get("versionName") or "").strip()
            output.append(InstalledContentItem(
                item_id=cls._item_id(cls.MODPACK, provider, project_id, name, ""),
                content_type=cls.MODPACK,
                name=name,
                version=version,
                provider=provider,
                project_id=project_id,
                version_id=version_id,
                file_id=str(data.get("fileId") or "").strip(),
                file_name="",
                target_path=".",
                enabled=True,
                managed_by_modpack=False,
                source_pack_provider="",
                size=total_size,
                sha1="",
                sha512="",
                project_url=cls._project_url(provider, project_id, cls.MODPACK),
                status=status,
                toggleable=False,
                removable=False,
            ))
        return output

    @staticmethod
    def _provider(value: object) -> str:
        normalized = str(value or "local").strip().casefold()
        return normalized if normalized in {"modrinth", "curseforge", "ftb", "local", "manual", "unknown"} else "unknown"

    @staticmethod
    def _item_id(content_type: str, provider: str, project_id: str, file_name: str, sha512_value: str) -> str:
        identity = str(project_id).strip() or str(sha512_value).strip().casefold() or Path(str(file_name)).name.casefold()
        digest = sha256(f"{content_type}:{provider}:{identity}".encode("utf-8")).hexdigest()[:24]
        return f"{content_type}:{digest}"

    @staticmethod
    def _project_url(provider: str, project_id: str, content_type: str) -> str:
        project = str(project_id).strip()
        if not project:
            return ""
        if provider == "modrinth":
            slug = "modpack" if content_type == InstalledContentLibraryManager.MODPACK else "mod"
            return f"https://modrinth.com/{slug}/{project}"
        return ""

    @staticmethod
    def _relative_to_instance(instance: Instance, path: Path) -> str:
        root = Path(instance.instance_dir).resolve(strict=False)
        target = Path(path).resolve(strict=False)
        try:
            return target.relative_to(root).as_posix()
        except ValueError:
            return f"mods/{Path(path).name}"

    @staticmethod
    def _safe_relative(value: str, fallback: str) -> str:
        normalized = str(value or fallback).replace("\\", "/").strip().lstrip("/")
        candidate = PurePosixPath(normalized)
        if not normalized or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            return fallback
        if candidate.parts and ":" in candidate.parts[0]:
            return fallback
        return candidate.as_posix()

    @staticmethod
    def _safe_instance_path(instance: Instance, relative_path: str) -> Path:
        root = Path(instance.instance_dir).resolve(strict=False)
        normalized = InstalledContentLibraryManager._safe_relative(relative_path, ".")
        target = root.joinpath(*PurePosixPath(normalized).parts).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise RuntimeError("Content path escapes the instance folder.") from error
        return target

    @staticmethod
    def _entry_id_from_item(item: InstalledContentItem) -> str:
        prefix = "content-pack:"
        if not item.item_id.startswith(prefix):
            raise RuntimeError("The selected content item is not a registered content pack.")
        return item.item_id[len(prefix):]

    @staticmethod
    def _int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _sort_key(item: InstalledContentItem) -> tuple:
        type_order = {"modpack": 0, "mod": 1, "resourcepack": 2, "shader": 3}
        status_order = {"broken": 0, "missing": 1, "pending": 2, "disabled": 3, "ready": 4}
        return (not item.pinned, type_order.get(item.content_type, 99), status_order.get(item.status, 99), item.name.casefold(), item.file_name.casefold())
