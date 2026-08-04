from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from shutil import copy2
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, is_zipfile
import hashlib
import json
import stat

from src.core.content.content_pack_registry import ContentPackRegistry
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader
from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.content.content_pack import ContentPackEntry, ContentPackInstallResult
from src.models.curseforge.file import CurseForgeFile
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage


class ContentPackManager:
    RESOURCE_PACK = "resourcepack"
    SHADER_PACK = "shader"
    SUPPORTED_TYPES = frozenset({RESOURCE_PACK, SHADER_PACK})
    MAX_ARCHIVE_ENTRIES = 20_000
    MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024

    @classmethod
    def list_entries(cls, instance: Instance, content_type: str = "") -> list[ContentPackEntry]:
        kinds = (cls.normalize_type(content_type),) if content_type else tuple(sorted(cls.SUPPORTED_TYPES))
        for kind in kinds:
            cls._discover_unregistered(instance, kind)
        return ContentPackRegistry.entries(instance, kinds[0] if len(kinds) == 1 else "")

    @classmethod
    def install_modrinth(cls, instance: Instance, content_type: str, version_id: str, reporter: ProgressReporter | None = None) -> ContentPackInstallResult:
        kind = cls.normalize_type(content_type)
        version = ModrinthClient.get_version(version_id)
        project = ModrinthClient.get_project(version.project_id)
        if project.project_type != kind:
            raise RuntimeError(f"'{project.title}' is not a Modrinth {cls.display_name(kind)} project.")
        file = version.primary_file(".zip")
        cache_path = cls._cache_path("modrinth", kind, version.project_id, version.version_id, file.filename)
        project_url = project.project_url or f"https://modrinth.com/{kind}/{project.slug or project.project_id}"
        version_url = f"{project_url}/version/{version.version_id}"
        ModrinthDownloader.download_file(file, cache_path, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_CONTENT, progress_message=f"Downloading {project.title}...", purpose=kind, page_url=version_url, project_url=project_url, project_id=version.project_id, version_id=version.version_id)
        return cls._install_verified_file(
            instance,
            kind,
            cache_path,
            provider="modrinth",
            project_id=version.project_id,
            version_id=version.version_id,
            file_id=file.filename,
            project_name=project.title,
            version_number=version.version_number,
            sha1=file.sha1,
            sha512=file.sha512,
            size=file.size,
            source_url=file.url,
            project_url=project_url,
        )

    @classmethod
    def install_curseforge(cls, instance: Instance, content_type: str, file: CurseForgeFile, project_name: str = "", project_url: str = "", reporter: ProgressReporter | None = None) -> ContentPackInstallResult:
        kind = cls.normalize_type(content_type)
        name = str(project_name).strip() or f"CurseForge project {file.project_id}"
        canonical_url = str(project_url).strip() or cls.curseforge_project_url(kind, file.project_id)
        cache_path = cls._cache_path("curseforge", kind, str(file.project_id), str(file.file_id), file.file_name)
        CurseForgeDownloader.download_file(file, cache_path, reporter=reporter, stage=ProgressStage.DOWNLOADING_CONTENT, message=f"Downloading {name}...", project_name=name, purpose=kind, managed_kind=kind, project_url=canonical_url)
        return cls._install_verified_file(
            instance,
            kind,
            cache_path,
            provider="curseforge",
            project_id=str(file.project_id),
            version_id=str(file.file_id),
            file_id=str(file.file_id),
            project_name=name,
            version_number=file.version_number,
            sha1=file.sha1,
            sha512="",
            size=file.file_length,
            source_url=file.download_url,
            project_url=canonical_url,
        )

    @classmethod
    def import_local(cls, instance: Instance, content_type: str, source: Path) -> ContentPackInstallResult:
        kind = cls.normalize_type(content_type)
        path = Path(source)
        if not path.is_file():
            raise RuntimeError(f"Content file does not exist: {path}")
        sha1, sha512, size = cls._hashes(path)
        return cls._install_verified_file(
            instance,
            kind,
            path,
            provider="local",
            project_id="",
            version_id="",
            file_id="",
            project_name=path.stem,
            version_number="",
            sha1=sha1,
            sha512=sha512,
            size=size,
            source_url="",
            project_url="",
        )

    @classmethod
    def set_enabled(cls, instance: Instance, entry_id: str, enabled: bool) -> ContentPackEntry:
        cls._assert_destructive_change_allowed(instance)
        entries = {entry.entry_id: entry for entry in ContentPackRegistry.entries(instance)}
        entry = entries.get(str(entry_id).strip())
        if entry is None:
            raise RuntimeError("The selected content pack is no longer registered.")
        if entry.enabled == bool(enabled):
            return entry
        active_dir = cls.destination_dir(instance, entry.content_type)
        disabled_dir = active_dir / ".disabled"
        disabled_dir.mkdir(parents=True, exist_ok=True)
        source = (active_dir if entry.enabled else disabled_dir) / entry.file_name
        destination = (active_dir if enabled else disabled_dir) / entry.file_name
        if not source.is_file():
            raise RuntimeError(f"Content file is missing: {source.name}")
        if destination.exists():
            raise RuntimeError(f"Cannot change content pack state because '{destination.name}' already exists in the destination folder.")
        source.replace(destination)
        updated = replace(entry, target_path=cls._relative_target(entry.content_type, entry.file_name, bool(enabled)), enabled=bool(enabled))
        try:
            ContentPackRegistry.upsert(instance, updated)
        except Exception:
            if destination.is_file() and not source.exists():
                destination.replace(source)
            raise
        return updated

    @classmethod
    def remove(cls, instance: Instance, entry_id: str) -> ContentPackEntry:
        cls._assert_destructive_change_allowed(instance)
        entry = next((item for item in ContentPackRegistry.entries(instance) if item.entry_id == str(entry_id).strip()), None)
        if entry is None:
            raise RuntimeError("The selected content pack is no longer registered.")
        active_dir = cls.destination_dir(instance, entry.content_type)
        for path in (active_dir / entry.file_name, active_dir / ".disabled" / entry.file_name):
            path.unlink(missing_ok=True)
        ContentPackRegistry.remove(instance, entry.entry_id)
        return entry

    @classmethod
    def destination_dir(cls, instance: Instance, content_type: str) -> Path:
        """Return the canonical Minecraft content directory for an instance.

        Instance directories are already the Minecraft game directory in MCW.  The
        v1.0.0 implementation accidentally added an extra ``minecraft`` segment.
        v1.0.1 migrates that legacy location before returning the canonical path.
        """
        kind = cls.normalize_type(content_type)
        cls.migrate_legacy_location(instance, kind)
        path = cls._destination_path(instance, kind)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def migrate_legacy_location(cls, instance: Instance, content_type: str = "") -> dict[str, object]:
        """Move v1.0.0 content from ``minecraft/<folder>`` to ``<folder>``.

        The migration is idempotent and never overwrites an existing destination.
        Conflicting files are left in the legacy folder and reported as skipped.
        Registry paths are normalized even when no files need to be moved.
        """
        kinds = (cls.normalize_type(content_type),) if content_type else tuple(sorted(cls.SUPPORTED_TYPES))
        moved: list[str] = []
        skipped: list[str] = []
        updated_entries = 0
        for kind in kinds:
            destination = cls._destination_path(instance, kind)
            legacy = cls._legacy_destination_path(instance, kind)
            destination.mkdir(parents=True, exist_ok=True)
            if legacy.is_dir() and legacy.resolve(strict=False) != destination.resolve(strict=False):
                for source in sorted(legacy.rglob("*"), key=lambda path: (len(path.parts), path.as_posix().casefold())):
                    if not source.is_file() or source.is_symlink():
                        continue
                    relative = source.relative_to(legacy)
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        skipped.append(relative.as_posix())
                        continue
                    source.replace(target)
                    moved.append(relative.as_posix())
                cls._remove_empty_tree(legacy)

            for entry in ContentPackRegistry.entries(instance, kind):
                normalized = cls._relative_target(kind, entry.file_name, entry.enabled)
                if cls._normalized_relative_path(entry.target_path) == cls._normalized_relative_path(normalized):
                    continue
                ContentPackRegistry.upsert(instance, replace(entry, target_path=normalized))
                updated_entries += 1
        return {"moved": tuple(moved), "skipped": tuple(skipped), "updatedRegistryEntries": updated_entries}

    @classmethod
    def _destination_path(cls, instance: Instance, content_type: str) -> Path:
        folder = "resourcepacks" if cls.normalize_type(content_type) == cls.RESOURCE_PACK else "shaderpacks"
        return Path(instance.instance_dir) / folder

    @classmethod
    def _legacy_destination_path(cls, instance: Instance, content_type: str) -> Path:
        folder = "resourcepacks" if cls.normalize_type(content_type) == cls.RESOURCE_PACK else "shaderpacks"
        return Path(instance.instance_dir) / "minecraft" / folder

    @staticmethod
    def _remove_empty_tree(root: Path) -> None:
        if not root.is_dir():
            return
        for directory in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda path: len(path.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass

    @classmethod
    def validate_archive(cls, source: Path, content_type: str) -> dict[str, object]:
        kind = cls.normalize_type(content_type)
        path = Path(source)
        if path.suffix.casefold() != ".zip" or not is_zipfile(path):
            raise RuntimeError(f"{cls.display_name(kind).title()} must be a valid .zip archive.")
        total_uncompressed = 0
        names: set[str] = set()
        has_resource_metadata = False
        has_shader_directory = False
        pack_format: int | None = None
        pack_description = ""
        try:
            with ZipFile(path) as archive:
                members = archive.infolist()
                if len(members) > cls.MAX_ARCHIVE_ENTRIES:
                    raise RuntimeError("The content archive contains too many files.")
                for member in members:
                    name = str(member.filename).replace("\\", "/")
                    cls._validate_member_name(name)
                    if name.casefold() in names:
                        raise RuntimeError(f"The content archive contains a duplicate path: {name}")
                    names.add(name.casefold())
                    mode = member.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        raise RuntimeError("Symbolic links are not allowed in content archives.")
                    total_uncompressed += max(0, int(member.file_size))
                    if total_uncompressed > cls.MAX_UNCOMPRESSED_BYTES:
                        raise RuntimeError("The content archive expands beyond the safe size limit.")
                    normalized = name.strip("/").casefold()
                    if normalized == "pack.mcmeta":
                        has_resource_metadata = True
                    if normalized == "shaders" or normalized.startswith("shaders/"):
                        has_shader_directory = True
                if kind == cls.RESOURCE_PACK:
                    if not has_resource_metadata:
                        raise RuntimeError("The resource pack does not contain pack.mcmeta at the archive root.")
                    pack_format, pack_description = cls._validate_pack_mcmeta(archive)
                elif not has_shader_directory:
                    raise RuntimeError("The shader pack does not contain a shaders directory at the archive root.")
        except BadZipFile as error:
            raise RuntimeError("The content archive is damaged or incomplete.") from error
        return {
            "contentType": kind,
            "entries": len(names),
            "uncompressedBytes": total_uncompressed,
            "packFormat": pack_format,
            "packDescription": pack_description,
        }

    @classmethod
    def normalize_type(cls, value: str) -> str:
        normalized = str(value).strip().lower().replace("_", "").replace("-", "")
        aliases = {"resourcepack": cls.RESOURCE_PACK, "resourcepacks": cls.RESOURCE_PACK, "shader": cls.SHADER_PACK, "shaderpack": cls.SHADER_PACK, "shaders": cls.SHADER_PACK}
        output = aliases.get(normalized, normalized)
        if output not in cls.SUPPORTED_TYPES:
            raise ValueError(f"Unsupported content type: {value or 'unknown'}")
        return output

    @classmethod
    def display_name(cls, content_type: str) -> str:
        return "resource pack" if cls.normalize_type(content_type) == cls.RESOURCE_PACK else "shader pack"

    @classmethod
    def curseforge_project_url(cls, content_type: str, project_id: int | str) -> str:
        slug = "texture-packs" if cls.normalize_type(content_type) == cls.RESOURCE_PACK else "shaders"
        return f"https://www.curseforge.com/minecraft/{slug}/{project_id}"

    @classmethod
    def _install_verified_file(cls, instance: Instance, content_type: str, source: Path, provider: str, project_id: str, version_id: str, file_id: str, project_name: str, version_number: str, sha1: str, sha512: str, size: int, source_url: str, project_url: str) -> ContentPackInstallResult:
        kind = cls.normalize_type(content_type)
        source_path = Path(source)
        archive_info = cls.validate_archive(source_path, kind)
        actual_sha1, actual_sha512, actual_size = cls._hashes(source_path)
        if size > 0 and actual_size != int(size):
            raise RuntimeError(f"Size mismatch for '{source_path.name}'.")
        if sha1 and actual_sha1.casefold() != str(sha1).casefold():
            raise RuntimeError(f"SHA-1 mismatch for '{source_path.name}'.")
        if sha512 and actual_sha512.casefold() != str(sha512).casefold():
            raise RuntimeError(f"SHA-512 mismatch for '{source_path.name}'.")

        destination_dir = cls.destination_dir(instance, kind)
        requested_name = cls._safe_file_name(source_path.name)
        entry_id = cls._entry_id(provider, project_id, version_id, requested_name, actual_sha512)
        registry_entries = ContentPackRegistry.entries(instance)
        previous = next((entry for entry in registry_entries if entry.entry_id == entry_id), None)
        file_name = requested_name
        destination = destination_dir / file_name
        source_is_destination = cls._same_path(source_path, destination)
        previous_owns_destination = previous is not None and previous.file_name.casefold() == file_name.casefold()
        if destination.exists() and not source_is_destination and not previous_owns_destination:
            file_name = cls._available_file_name(destination_dir, requested_name)
            destination = destination_dir / file_name
            source_is_destination = cls._same_path(source_path, destination)

        replaced = previous is not None
        if InstanceRunLock.is_active(instance) and (replaced or destination.exists()):
            raise RuntimeError(
                "Minecraft is running. New resource packs and shader packs may be added, "
                "but an existing pack cannot be replaced until the game is closed."
            )
        staging = destination.with_name(f".{destination.stem}.{uuid4().hex}.installing.zip")
        backup = destination.with_name(f".{destination.stem}.{uuid4().hex}.backup.zip")
        staging.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        moved_existing = False
        try:
            if not source_is_destination:
                if destination.exists():
                    destination.replace(backup)
                    moved_existing = True
                copy2(source_path, staging)
                cls.validate_archive(staging, kind)
                staging.replace(destination)

            entry = ContentPackEntry(
                entry_id=entry_id,
                content_type=kind,
                provider=str(provider).strip().lower() or "local",
                project_id=str(project_id).strip(),
                version_id=str(version_id).strip(),
                file_id=str(file_id).strip(),
                project_name=str(project_name).strip() or Path(file_name).stem,
                version_number=str(version_number).strip(),
                pack_format=archive_info.get("packFormat") if isinstance(archive_info.get("packFormat"), int) else None,
                pack_description=str(archive_info.get("packDescription") or "").strip(),
                file_name=file_name,
                target_path=cls._relative_target(kind, file_name, True),
                sha1=actual_sha1,
                sha512=actual_sha512,
                size=actual_size,
                source_url=cls._safe_https_url(source_url),
                project_url=cls._safe_https_url(project_url),
                installed_at=datetime.now(timezone.utc).isoformat(),
                enabled=True,
            )
            ContentPackRegistry.upsert(instance, entry)
        except Exception:
            if not source_is_destination:
                destination.unlink(missing_ok=True)
                if moved_existing and backup.is_file():
                    backup.replace(destination)
            raise
        else:
            backup.unlink(missing_ok=True)
            if previous is not None and previous.file_name.casefold() != file_name.casefold():
                (destination_dir / previous.file_name).unlink(missing_ok=True)
                (destination_dir / ".disabled" / previous.file_name).unlink(missing_ok=True)
            return ContentPackInstallResult(instance_name=instance.name, content_type=kind, provider=entry.provider, project_name=entry.project_name, file_name=file_name, target_path=entry.target_path, replaced=replaced)
        finally:
            staging.unlink(missing_ok=True)
            backup.unlink(missing_ok=True)

    @classmethod
    def _discover_unregistered(cls, instance: Instance, content_type: str) -> None:
        kind = cls.normalize_type(content_type)
        destination_dir = cls.destination_dir(instance, kind)
        entries = ContentPackRegistry.entries(instance, kind)
        registered_paths = {
            cls._normalized_relative_path(entry.target_path)
            for entry in entries
            if entry.target_path
        }
        changed = False
        for enabled, directory in ((True, destination_dir), (False, destination_dir / ".disabled")):
            if not directory.is_dir():
                continue
            try:
                candidates = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.casefold() == ".zip"), key=lambda path: path.name.casefold())
            except OSError:
                continue
            for path in candidates:
                relative_target = cls._relative_target(kind, path.name, enabled)
                if cls._normalized_relative_path(relative_target) in registered_paths:
                    continue
                try:
                    archive_info = cls.validate_archive(path, kind)
                    sha1, sha512, size = cls._hashes(path)
                except (OSError, RuntimeError):
                    continue
                entry = ContentPackEntry(
                    entry_id=cls._entry_id("local", "", "", path.name, sha512),
                    content_type=kind,
                    provider="local",
                    project_id="",
                    version_id="",
                    file_id="",
                    project_name=path.stem,
                    version_number="",
                    pack_format=archive_info.get("packFormat") if isinstance(archive_info.get("packFormat"), int) else None,
                    pack_description=str(archive_info.get("packDescription") or "").strip(),
                    file_name=path.name,
                    target_path=relative_target,
                    sha1=sha1,
                    sha512=sha512,
                    size=size,
                    source_url="",
                    project_url="",
                    installed_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    enabled=enabled,
                )
                ContentPackRegistry.upsert(instance, entry)
                registered_paths.add(cls._normalized_relative_path(relative_target))
                changed = True
        if changed:
            entries = ContentPackRegistry.entries(instance, kind)
        for entry in entries:
            if entry.provider != "local":
                continue
            active = destination_dir / entry.file_name
            disabled = destination_dir / ".disabled" / entry.file_name
            if not active.is_file() and not disabled.is_file():
                ContentPackRegistry.remove(instance, entry.entry_id)

    @staticmethod
    def _normalized_relative_path(value: str) -> str:
        return str(value).replace("\\", "/").strip("/").casefold()

    @staticmethod
    def _assert_destructive_change_allowed(instance: Instance) -> None:
        if InstanceRunLock.is_active(instance):
            raise RuntimeError(
                "Close Minecraft before disabling, enabling, removing, or replacing a resource pack or shader pack. "
                "The selected content may currently be in use."
            )

    @staticmethod
    def _hashes(path: Path) -> tuple[str, str, int]:
        sha1 = hashlib.sha1(usedforsecurity=False)
        sha512 = hashlib.sha512()
        size = 0
        with Path(path).open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size += len(chunk)
                sha1.update(chunk)
                sha512.update(chunk)
        return sha1.hexdigest(), sha512.hexdigest(), size

    @staticmethod
    def _validate_member_name(name: str) -> None:
        if not name or "\x00" in name:
            raise RuntimeError("The content archive contains an invalid path.")
        path = PurePosixPath(name)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise RuntimeError(f"Unsafe content archive path: {name}")
        if path.parts and ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe content archive path: {name}")

    @staticmethod
    def _validate_pack_mcmeta(archive: ZipFile) -> tuple[int, str]:
        try:
            raw = archive.read("pack.mcmeta")
            payload = json.loads(raw.decode("utf-8-sig"))
        except (KeyError, UnicodeError, ValueError, TypeError) as error:
            raise RuntimeError("The resource pack contains an invalid pack.mcmeta file.") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("pack"), dict):
            raise RuntimeError("The resource pack contains an invalid pack.mcmeta file.")
        pack_format = payload["pack"].get("pack_format")
        if not isinstance(pack_format, int) or pack_format < 1:
            raise RuntimeError("The resource pack pack.mcmeta does not contain a valid pack_format.")
        description = payload["pack"].get("description", "")
        if isinstance(description, str):
            normalized_description = description.strip()
        elif description is None:
            normalized_description = ""
        else:
            normalized_description = json.dumps(description, ensure_ascii=False, separators=(",", ":"))
        return pack_format, normalized_description

    @staticmethod
    def _safe_file_name(value: str) -> str:
        raw_name = PurePosixPath(str(value).replace("\\", "/")).name.strip().rstrip(". ")
        if not raw_name or raw_name in {".", ".."} or not raw_name.casefold().endswith(".zip"):
            raise RuntimeError("Content pack file name must end in .zip.")
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if character in invalid or ord(character) < 32 else character for character in raw_name)
        stem = Path(cleaned).stem.rstrip(". ")[:160]
        if not stem:
            stem = "content-pack"
        if stem.casefold() in {"con", "prn", "aux", "nul", *(f"com{index}" for index in range(1, 10)), *(f"lpt{index}" for index in range(1, 10))}:
            stem = f"_{stem}"
        return f"{stem}.zip"

    @staticmethod
    def _safe_https_url(value: str) -> str:
        raw = str(value or "").strip()
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return ""
        if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
            return ""
        try:
            host = parsed.hostname.encode("idna").decode("ascii").casefold()
            parsed_port = parsed.port
        except (UnicodeError, ValueError):
            return ""
        port = f":{parsed_port}" if parsed_port is not None else ""
        return urlunsplit(("https", f"{host}{port}", parsed.path or "/", "", ""))

    @staticmethod
    def _entry_id(provider: str, project_id: str, version_id: str, file_name: str, sha512: str = "") -> str:
        normalized_provider = str(provider).strip().lower() or "local"
        normalized_project = str(project_id).strip()
        normalized_version = str(version_id).strip()
        if normalized_project:
            identity = f"{normalized_provider}:project:{normalized_project}"
        elif normalized_version:
            identity = f"{normalized_provider}:version:{normalized_version}"
        else:
            identity = f"local:sha512:{str(sha512).strip().lower() or 'unknown'}:name:{file_name.casefold()}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _same_path(first: Path, second: Path) -> bool:
        try:
            return first.resolve(strict=False) == second.resolve(strict=False)
        except OSError:
            return False

    @staticmethod
    def _available_file_name(directory: Path, requested_name: str) -> str:
        original = Path(requested_name)
        disabled_dir = directory / ".disabled"
        for index in range(2, 10_000):
            candidate = f"{original.stem} ({index}){original.suffix}"
            if not (directory / candidate).exists() and not (disabled_dir / candidate).exists():
                return candidate
        raise RuntimeError(f"Could not allocate a safe destination name for '{requested_name}'.")

    @staticmethod
    def _relative_target(content_type: str, file_name: str, enabled: bool) -> str:
        folder = "resourcepacks" if content_type == ContentPackManager.RESOURCE_PACK else "shaderpacks"
        if enabled:
            return f"{folder}/{file_name}"
        return f"{folder}/.disabled/{file_name}"

    @classmethod
    def _cache_path(cls, provider: str, content_type: str, project_id: str, version_id: str, file_name: str) -> Path:
        normalized_provider = str(provider).strip().lower()
        if normalized_provider not in {"modrinth", "curseforge"}:
            normalized_provider = "provider"
        kind = cls.normalize_type(content_type)
        identity = hashlib.sha256(f"{normalized_provider}:{project_id}:{version_id}".encode("utf-8")).hexdigest()[:32]
        try:
            safe_name = cls._safe_file_name(file_name)
        except RuntimeError:
            safe_name = f"{uuid4().hex}.zip"
        path = Paths.CACHE_ROOT / "content" / normalized_provider / kind / identity / safe_name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
