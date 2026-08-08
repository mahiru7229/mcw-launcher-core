from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.core.fs.paths import Paths
from src.core.instance.instance_run_lock import InstanceRunLock
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.network.artifact_download_service import artifact_download_service
from src.models.instance.instance import Instance
from src.models.modrinth.manual_download import ModrinthManualDownload
from src.models.modrinth.manual_import_result import ModrinthManualImportedFile, ModrinthManualImportResult
from src.models.network.artifact import ArtifactRequest


class ModrinthManualInstaller:
    @staticmethod
    def install(instance: Instance, requirement: ModrinthManualDownload, source: Path, launch_lock_token: str | None = None) -> str:
        owns_preparing_lock = InstanceRunLock.owns_preparing_lock(instance, launch_lock_token)
        if InstanceRunLock.is_active(instance) and not owns_preparing_lock:
            raise RuntimeError("Close Minecraft before importing a manually downloaded file.")
        path = Path(source)
        if not path.is_file():
            raise RuntimeError("The selected Modrinth file does not exist.")
        if requirement.managed_kind == "pack":
            return ModrinthManualInstaller._install_pack_file(instance, requirement, path, allow_while_paused=owns_preparing_lock)
        if Path(requirement.file_name).suffix.casefold() != ".jar":
            raise RuntimeError("A standalone mod must be a .jar file.")
        cache = Paths.modrinth_file_cache(requirement.project_id, requirement.version_id, requirement.file_name)
        artifact_download_service.accept_manual_file(ModrinthManualInstaller._request(requirement, cache), path, allow_while_paused=owns_preparing_lock)
        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
        metadata = ModManager.read_mod(cache, preferred_loader=loader_name)
        compatibility_warning = ModManager.compatibility_warning(instance, metadata)
        added = ModManager.add_mods(instance, [cache], replace=True, launch_lock_token=launch_lock_token, allow_unverified=True, managed_source=True)
        if not added:
            raise RuntimeError("The selected file could not be added to the instance.")
        installed_name = added[0].file_name
        ModrinthManualInstaller._save_mod_file(instance, requirement, installed_name, compatibility_warning)
        return installed_name

    @staticmethod
    def install_many(instance: Instance, requirements: tuple[ModrinthManualDownload, ...] | list[ModrinthManualDownload], sources: tuple[Path, ...] | list[Path], launch_lock_token: str | None = None) -> ModrinthManualImportResult:
        allow_while_paused = InstanceRunLock.owns_preparing_lock(instance, launch_lock_token)
        pending = list(requirements)
        imported: list[ModrinthManualImportedFile] = []
        added_mods: list[str] = []
        rejected: list[str] = []
        for source_value in sources:
            source = Path(source_value)
            if not source.is_file():
                rejected.append(f"{source.name}: The selected file is not readable.")
                continue
            requirement = ModrinthManualInstaller._match_requirement(source, pending, allow_while_paused=allow_while_paused)
            if requirement is not None:
                try:
                    installed_name = ModrinthManualInstaller.install(instance, requirement, source, launch_lock_token=launch_lock_token)
                except Exception as error:
                    rejected.append(f"{source.name}: {error}")
                else:
                    imported.append(ModrinthManualImportedFile(requirement=requirement, installed_name=installed_name))
                    pending.remove(requirement)
                continue
            if source.suffix.casefold() != ".jar":
                rejected.append(f"{source.name}: This file is not listed by the modpack. Only unmatched .jar files can be added as extra mods.")
                continue
            try:
                added = ModManager.add_mods(instance, [source], replace=False, launch_lock_token=launch_lock_token, allow_unverified=True)
                added_mods.extend(item.file_name for item in added)
            except Exception as error:
                rejected.append(f"{source.name}: {error}")
        return ModrinthManualImportResult(imported=tuple(imported), added_mods=tuple(added_mods), rejected=tuple(rejected))

    @staticmethod
    def _match_requirement(source: Path, requirements: list[ModrinthManualDownload], allow_while_paused: bool = False) -> ModrinthManualDownload | None:
        for requirement in requirements:
            request = ModrinthManualInstaller._request(requirement, Path(requirement.file_name))
            try:
                artifact_download_service.verify_manual_file(request, source, allow_while_paused=allow_while_paused)
            except Exception:
                continue
            return requirement
        return None

    @staticmethod
    def _install_pack_file(instance: Instance, requirement: ModrinthManualDownload, source: Path, allow_while_paused: bool = False) -> str:
        relative = ModrinthPackRegistry._safe_relative(requirement.managed_path)
        if relative is None:
            raise RuntimeError(f"Unsafe managed Modrinth path: {requirement.managed_path!r}")
        target = Path(instance.instance_dir).joinpath(*relative.parts)
        artifact_download_service.accept_manual_file(ModrinthManualInstaller._request(requirement, target), source, allow_while_paused=allow_while_paused)
        pack = ModrinthPackRegistry.load(instance)
        updated = False
        for entry in pack.get("managedFiles", []):
            if not isinstance(entry, dict) or str(entry.get("path") or "").casefold() != relative.as_posix().casefold():
                continue
            entry["sha1"] = requirement.sha1
            entry["sha512"] = requirement.sha512
            entry["size"] = requirement.file_size
            entry.pop("downloadFailure", None)
            updated = True
            break
        if not updated:
            target.unlink(missing_ok=True)
            raise RuntimeError("The selected file is no longer listed in this Modrinth modpack.")
        pack["verificationCache"] = ModrinthPackRegistry.build_verification_cache(instance.instance_dir, pack.get("managedFiles", []))
        pack["lastDownloadFailures"] = [item for item in pack.get("lastDownloadFailures", []) if not (isinstance(item, dict) and str(item.get("path") or "").casefold() == relative.as_posix().casefold())]
        ModrinthPackRegistry.save(instance.instance_dir, pack)
        return target.name

    @staticmethod
    def _save_mod_file(instance: Instance, requirement: ModrinthManualDownload, installed_name: str, compatibility_warning: str) -> None:
        registry = ModrinthRegistry.load(instance)
        mods = registry.setdefault("mods", {})
        previous = mods.get(requirement.project_id, {}) if isinstance(mods.get(requirement.project_id), dict) else {}
        old_name = str(previous.get("fileName") or "")
        if old_name and old_name.casefold() != installed_name.casefold():
            old_path = ModrinthRegistry.safe_tracked_path(instance, old_name)
            if old_path is not None:
                old_path.unlink(missing_ok=True)
                old_path.with_name(old_path.name + ModManager.DISABLED_SUFFIX).unlink(missing_ok=True)
        mods[requirement.project_id] = {
            **previous,
            "projectId": requirement.project_id,
            "versionId": requirement.version_id,
            "fileName": installed_name,
            "title": requirement.project_name,
            "sha1": requirement.sha1,
            "sha512": requirement.sha512,
            "size": requirement.file_size,
            "downloadUrls": [requirement.direct_url] if requirement.direct_url else [],
            "source": "modrinth",
            "pendingDownload": False,
            "lastDownloadError": "",
            "acceptedUnverified": bool(compatibility_warning),
            "compatibilityWarning": compatibility_warning,
            "manualImport": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        mods[requirement.project_id].pop("downloadFailure", None)
        ModrinthRegistry.save(instance, registry)

    @staticmethod
    def _request(requirement: ModrinthManualDownload, destination: Path) -> ArtifactRequest:
        hashes = {key: value for key, value in {"sha1": requirement.sha1, "sha512": requirement.sha512}.items() if value}
        return ArtifactRequest(
            provider="modrinth",
            purpose="manual-modpack-artifact" if requirement.managed_kind == "pack" else "manual-mod",
            destination=destination,
            urls=(requirement.direct_url,) if requirement.direct_url else (),
            page_url=requirement.version_url,
            project_url=requirement.project_url,
            expected_filename=requirement.file_name,
            expected_size=requirement.file_size,
            hashes=hashes,
            project_id=requirement.project_id,
            version_id=requirement.version_id,
        )
