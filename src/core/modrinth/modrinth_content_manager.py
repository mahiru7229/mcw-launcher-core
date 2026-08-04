from __future__ import annotations

from pathlib import Path
import zipfile

from src.core.fs.paths import Paths
from src.core.mod.mod_manager import ModManager
from src.core.modrinth.modrinth_client import ModrinthClient
from src.core.modrinth.modrinth_downloader import ModrinthDownloader
from src.core.modrinth.modrinth_errors import ModrinthManagedFilesRequired
from src.core.modrinth.modrinth_pack_installer import ModrinthPackInstaller
from src.core.modrinth.modrinth_pack_registry import ModrinthPackRegistry
from src.core.modrinth.modrinth_registry import ModrinthRegistry
from src.core.network.artifact_download_service import ArtifactDownloadError
from src.core.network.download_pause import download_pause_controller, is_download_paused
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.modrinth.manual_download import ModrinthManualDownload
from src.models.progress.progress_stage import ProgressStage


class ModrinthContentManager:
    MAX_DOWNLOAD_ROUNDS = 3
    MAX_DOWNLOAD_WORKERS = 8
    PROGRESS_EMIT_INTERVAL_SECONDS = 0.08

    @staticmethod
    def ensure(instance: Instance, reporter: ProgressReporter | None = None, block_launch_on_failure: bool = True, launch_lock_token: str | None = None) -> tuple[str, ...]:
        if getattr(instance, "instance_dir", None) is None:
            return ()

        pack_registry = ModrinthPackRegistry.load(instance)
        mod_registry = ModrinthRegistry.load(instance)
        pack_entries = ModrinthContentManager._pack_download_entries(pack_registry)
        mod_entries = ModrinthContentManager._mod_entries(mod_registry)
        if not pack_entries and not mod_entries:
            return ()

        warnings: list[str] = []
        if pack_entries and any(not entry.get("downloads") for entry in pack_entries):
            try:
                ModrinthContentManager._hydrate_pack_downloads(instance, pack_registry, reporter)
                pack_entries = ModrinthContentManager._pack_download_entries(pack_registry)
            except Exception as error:
                if is_download_paused(error):
                    raise
                ModrinthContentManager._append_warning(warnings, f"Could not refresh Modrinth pack download sources: {error}")

        last_pack_errors: dict[str, str] = {}
        last_mod_errors: dict[str, str] = {}

        for round_number in range(1, ModrinthContentManager.MAX_DOWNLOAD_ROUNDS + 1):
            check_suffix = "" if round_number == 1 else f" after download round {round_number - 1}/{ModrinthContentManager.MAX_DOWNLOAD_ROUNDS}"
            missing_pack = ModrinthContentManager._check_pack_files(instance, pack_registry, pack_entries, warnings, reporter, check_suffix)
            missing_mods, mod_changed = ModrinthContentManager._check_mod_files(instance, mod_entries, warnings, reporter, check_suffix)
            if mod_changed:
                ModrinthRegistry.save(instance, mod_registry)

            if not missing_pack and not missing_mods:
                if pack_registry:
                    pack_registry["lastDownloadFailures"] = []
                    ModrinthPackRegistry.save(instance.instance_dir, pack_registry)
                return tuple(warnings)

            ModManager.ensure_modifiable(instance, launch_lock_token)
            last_pack_errors = ModrinthContentManager._download_pack_round(missing_pack, reporter, round_number)
            last_mod_errors = ModrinthContentManager._download_mod_round(instance, missing_mods, reporter, round_number, launch_lock_token)
            if pack_registry:
                pack_registry["lastDownloadFailures"] = ModrinthContentManager._pack_failure_payload(missing_pack, last_pack_errors)
                ModrinthPackRegistry.save(instance.instance_dir, pack_registry)
            if mod_entries:
                ModrinthRegistry.save(instance, mod_registry)

        missing_pack = ModrinthContentManager._check_pack_files(instance, pack_registry, pack_entries, warnings, reporter, f" after download round {ModrinthContentManager.MAX_DOWNLOAD_ROUNDS}/{ModrinthContentManager.MAX_DOWNLOAD_ROUNDS}")
        missing_mods, mod_changed = ModrinthContentManager._check_mod_files(instance, mod_entries, warnings, reporter, f" after download round {ModrinthContentManager.MAX_DOWNLOAD_ROUNDS}/{ModrinthContentManager.MAX_DOWNLOAD_ROUNDS}")
        if mod_changed or mod_entries:
            ModrinthRegistry.save(instance, mod_registry)

        if not missing_pack and not missing_mods:
            if pack_registry:
                pack_registry["lastDownloadFailures"] = []
                ModrinthPackRegistry.save(instance.instance_dir, pack_registry)
            return tuple(warnings)

        pack_failures = ModrinthContentManager._pack_failure_payload(missing_pack, last_pack_errors)
        if pack_registry:
            pack_registry["lastDownloadFailures"] = pack_failures
            ModrinthPackRegistry.save(instance.instance_dir, pack_registry)

        labels: list[str] = []
        for item in pack_failures:
            labels.append(f"{item['path']}: {item['error']}")
        for entry in missing_mods:
            title = ModrinthContentManager._mod_title(entry)
            filename = Path(str(entry.get("fileName") or "")).name
            destination = f"mods/{filename}" if filename else title
            error = last_mod_errors.get(ModrinthContentManager._mod_key(entry)) or str(entry.get("lastDownloadError") or "File is still missing after retries")
            entry["pendingDownload"] = True
            entry["lastDownloadError"] = error
            labels.append(f"{destination} ({title}): {error}")
        if missing_mods:
            ModrinthRegistry.save(instance, mod_registry)

        count = len(missing_pack) + len(missing_mods)
        details = "; ".join(labels)
        if block_launch_on_failure:
            requirements = ModrinthContentManager._manual_requirements(pack_registry, missing_pack, missing_mods)
            message = f"Could not download {count} required Modrinth file(s) after {ModrinthContentManager.MAX_DOWNLOAD_ROUNDS} rounds: {details}."
            if requirements:
                raise ModrinthManagedFilesRequired(instance, requirements, message)
            raise RuntimeError(message)

        ModrinthContentManager._append_warning(
            warnings,
            f"Launching with {count} missing Modrinth file(s). Download them manually and place them in the listed instance paths: {details}",
        )
        ModrinthContentManager._append_warning(
            warnings,
            "Automatic Modrinth blocking is disabled by the resolved launcher/instance policy. Re-enable it under Managed modpack file checks.",
        )
        return tuple(warnings)

    @staticmethod
    def _pack_download_entries(registry: dict) -> list[dict]:
        managed_files = registry.get("managedFiles", []) if isinstance(registry.get("managedFiles"), list) else []
        return [entry for entry in managed_files if isinstance(entry, dict) and str(entry.get("source") or "") == "download"]

    @staticmethod
    def _mod_entries(registry: dict) -> list[dict]:
        mods = registry.get("mods", {}) if isinstance(registry.get("mods"), dict) else {}
        return [entry for entry in mods.values() if isinstance(entry, dict)]

    @staticmethod
    def _check_pack_files(instance: Instance, registry: dict, entries: list[dict], warnings: list[str], reporter: ProgressReporter | None, suffix: str) -> list[dict]:
        total = len(entries)
        message = f"Checking Modrinth modpack files{suffix}..."
        ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODPACK, message, 0, total)
        missing: list[dict] = []
        root = Path(instance.instance_dir)
        cache = ModrinthPackRegistry._normalize_verification_cache(registry.get("verificationCache", {}), registry.get("managedFiles", []))
        registry["verificationCache"] = cache

        for completed, entry in enumerate(entries, start=1):
            relative = ModrinthPackRegistry._safe_relative(str(entry.get("path") or ""))
            if relative is None:
                missing.append({"entry": entry, "path": str(entry.get("path") or "<invalid path>"), "target": None})
                ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODPACK, message, completed, total)
                continue

            target = root.joinpath(*relative.parts)
            verified, _, _ = ModrinthPackRegistry.verify_entry(root, entry, cache=cache)
            if verified:
                ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODPACK, message, completed, total)
                continue

            if target.exists():
                ModrinthContentManager._append_warning(warnings, f"Preserved modified Modrinth pack file: {relative.as_posix()}")
            else:
                missing.append({"entry": entry, "path": relative.as_posix(), "target": target})
            ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODPACK, message, completed, total)

        return missing

    @staticmethod
    def _check_mod_files(instance: Instance, entries: list[dict], warnings: list[str], reporter: ProgressReporter | None, suffix: str) -> tuple[list[dict], bool]:
        total = len(entries)
        message = f"Checking Modrinth mods{suffix}..."
        ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODS, message, 0, total)
        missing: list[dict] = []
        changed = False

        for completed, entry in enumerate(entries, start=1):
            filename = Path(str(entry.get("fileName") or "")).name
            target = ModrinthRegistry.safe_tracked_path(instance, filename)
            sha1 = str(entry.get("sha1") or "")
            sha512 = str(entry.get("sha512") or "")
            size = int(entry.get("size", 0) or 0)
            title = ModrinthContentManager._mod_title(entry)

            if target is None or not filename:
                changed |= ModrinthContentManager._set_mod_download_state(entry, True, "Invalid tracked filename")
                missing.append(entry)
            elif ModrinthDownloader.verify(target, sha1=sha1, sha512=sha512, expected_size=size):
                changed |= ModrinthContentManager._set_mod_download_state(entry, False, "")
            elif target.exists():
                warning = "The tracked file was modified and was preserved."
                changed |= ModrinthContentManager._set_mod_download_state(entry, False, warning)
                ModrinthContentManager._append_warning(warnings, f"{title}: {warning}")
            else:
                if not entry.get("pendingDownload"):
                    entry["pendingDownload"] = True
                    changed = True
                missing.append(entry)

            ModrinthContentManager._report_files(reporter, ProgressStage.CHECKING_MODS, message, completed, total)

        return missing, changed

    @staticmethod
    def _download_pack_round(missing: list[dict], reporter: ProgressReporter | None, round_number: int) -> dict[str, str]:
        total = len(missing)
        message = "Downloading modpack mods..."
        batch_progress = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_MODS, message=message, total=total, min_emit_interval_seconds=ModrinthContentManager.PROGRESS_EMIT_INTERVAL_SECONDS)
        batch_progress.start()
        errors: dict[str, str] = {}
        for item in missing:
            token = object()
            child_reporter = batch_progress.reporter_for(token)
            entry = item["entry"]
            path = str(item["path"])
            try:
                download_pause_controller.raise_if_requested()
                target = item["target"]
                if target is None:
                    raise RuntimeError("Unsafe managed path")
                urls = tuple(str(url).strip() for url in entry.get("downloads", []) if str(url).strip()) if isinstance(entry.get("downloads"), list) else ()
                ModrinthDownloader.download_urls(
                    urls=urls,
                    destination=target,
                    sha1=str(entry.get("sha1") or ""),
                    sha512=str(entry.get("sha512") or ""),
                    expected_size=int(entry.get("size", 0) or 0),
                    restrict_hosts=True,
                    max_retry=1,
                    reporter=child_reporter,
                    progress_stage=ProgressStage.DOWNLOADING_MODS,
                    progress_message=message,
                    purpose="modpack-artifact",
                )
                entry.pop("downloadFailure", None)
            except Exception as error:
                if is_download_paused(error):
                    raise
                errors[path] = str(error)
                if isinstance(error, ArtifactDownloadError):
                    entry["downloadFailure"] = error.failure.to_dict()
            finally:
                batch_progress.complete(token)
        return errors

    @staticmethod
    def _download_mod_round(instance: Instance, missing: list[dict], reporter: ProgressReporter | None, round_number: int, launch_lock_token: str | None = None) -> dict[str, str]:
        total = len(missing)
        message = "Downloading modpack mods..."
        batch_progress = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_MODS, message=message, total=total, min_emit_interval_seconds=ModrinthContentManager.PROGRESS_EMIT_INTERVAL_SECONDS)
        batch_progress.start()
        errors: dict[str, str] = {}
        for entry in missing:
            token = object()
            child_reporter = batch_progress.reporter_for(token)
            key = ModrinthContentManager._mod_key(entry)
            try:
                download_pause_controller.raise_if_requested()
                project_id = str(entry.get("projectId") or "").strip()
                version_id = str(entry.get("versionId") or "").strip()
                urls = tuple(str(url).strip() for url in entry.get("downloadUrls", []) if str(url).strip()) if isinstance(entry.get("downloadUrls"), list) else ()
                if not urls:
                    try:
                        ModrinthContentManager._hydrate_mod_download(entry)
                    except Exception:
                        pass
                    project_id = str(entry.get("projectId") or "").strip()
                    version_id = str(entry.get("versionId") or "").strip()
                    urls = tuple(str(url).strip() for url in entry.get("downloadUrls", []) if str(url).strip()) if isinstance(entry.get("downloadUrls"), list) else ()
                filename = Path(str(entry.get("fileName") or "")).name
                if not filename:
                    raise RuntimeError("Invalid tracked filename")
                cache_path = Paths.modrinth_file_cache(project_id, version_id, filename)
                title = ModrinthContentManager._mod_title(entry)
                project_url = f"https://modrinth.com/project/{project_id}" if project_id else ""
                version_url = f"{project_url}/version/{version_id}" if project_url and version_id else project_url
                downloaded_path = ModrinthDownloader.download_urls(
                    urls=urls,
                    destination=cache_path,
                    sha1=str(entry.get("sha1") or ""),
                    sha512=str(entry.get("sha512") or ""),
                    expected_size=int(entry.get("size", 0) or 0),
                    restrict_hosts=False,
                    max_retry=1,
                    reporter=child_reporter,
                    progress_stage=ProgressStage.DOWNLOADING_MODS,
                    progress_message=message,
                    purpose="mod",
                    page_url=version_url,
                    project_url=project_url,
                    project_id=project_id,
                    version_id=version_id,
                )
                metadata = ModManager.read_mod(downloaded_path, provider_version=str(entry.get("versionNumber") or ""))
                if launch_lock_token is None:
                    added = ModManager.add_mods(instance, [downloaded_path], replace=True)
                else:
                    added = ModManager.add_mods(instance, [downloaded_path], replace=True, launch_lock_token=launch_lock_token)
                if not added:
                    raise RuntimeError("The downloaded mod could not be added to the instance.")
                entry["fileName"] = added[0].file_name
                entry.pop("downloadFailure", None)
                ModrinthContentManager._set_mod_download_state(entry, False, "")
            except Exception as error:
                if is_download_paused(error):
                    raise
                error_message = str(error)
                errors[key] = error_message
                if isinstance(error, ArtifactDownloadError):
                    entry["downloadFailure"] = error.failure.to_dict()
                ModrinthContentManager._set_mod_download_state(entry, True, error_message)
            finally:
                batch_progress.complete(token)
        return errors

    @staticmethod
    def _hydrate_pack_downloads(instance: Instance, registry: dict, reporter: ProgressReporter | None) -> None:
        project_id = str(registry.get("projectId") or "").strip()
        version_id = str(registry.get("versionId") or "").strip()
        if not project_id or not version_id:
            raise RuntimeError("The Modrinth pack registry is missing project or version information.")

        version = ModrinthClient.get_version(version_id)
        if version.project_id != project_id:
            raise RuntimeError("The saved Modrinth pack version no longer matches its project.")
        pack_file = version.primary_file(".mrpack")
        pack_path = Paths.modrinth_pack_cache(project_id, version_id, pack_file.filename)
        ModrinthDownloader.download_file(pack_file, pack_path, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODPACK, progress_message="Refreshing Modrinth modpack manifest...")

        with zipfile.ZipFile(pack_path, "r") as archive:
            index = ModrinthPackInstaller._read_index(archive)
            selected_files, _, _ = ModrinthPackInstaller._selected_files(index, bool(registry.get("installOptionalFiles", True)))
        refreshed = {entry["path"].casefold(): entry for entry in ModrinthPackInstaller._managed_download_entries(selected_files)}

        merged: list[dict] = []
        for entry in registry.get("managedFiles", []):
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("path") or "").casefold()
            replacement = refreshed.get(key)
            merged.append({**entry, **replacement} if replacement is not None else entry)
        registry["managedFiles"] = merged
        ModrinthPackRegistry.save(instance.instance_dir, registry)

    @staticmethod
    def _hydrate_mod_download(entry: dict) -> None:
        version_id = str(entry.get("versionId") or "").strip()
        project_id = str(entry.get("projectId") or "").strip()
        if not version_id:
            raise RuntimeError("The Modrinth registry is missing the version needed to retry this mod.")

        version = ModrinthClient.get_version(version_id)
        if project_id and version.project_id != project_id:
            raise RuntimeError("The saved Modrinth mod version no longer matches its project.")
        file = version.primary_file(".jar")
        entry["projectId"] = version.project_id
        entry["fileName"] = file.filename
        entry["sha1"] = file.sha1
        entry["sha512"] = file.sha512
        entry["size"] = file.size
        entry["downloadUrls"] = [file.url]

    @staticmethod
    def _pack_failure_payload(missing: list[dict], errors: dict[str, str]) -> list[dict]:
        failures: list[dict] = []
        for item in missing:
            path = str(item["path"])
            failures.append({"path": path, "error": errors.get(path, "File is still missing after retries")})
        return failures

    @staticmethod
    def _manual_requirements(pack_registry: dict, missing_pack: list[dict], missing_mods: list[dict]) -> tuple[ModrinthManualDownload, ...]:
        requirements: list[ModrinthManualDownload] = []
        pack_project = str(pack_registry.get("projectId") or "")
        pack_version = str(pack_registry.get("versionId") or "")
        pack_name = str(pack_registry.get("name") or "Modrinth modpack")
        for item in missing_pack:
            entry = item["entry"]
            path = str(item.get("path") or entry.get("path") or "")
            failure = entry.get("downloadFailure") if isinstance(entry.get("downloadFailure"), dict) else {}
            urls = tuple(str(url).strip() for url in entry.get("downloads", []) if str(url).strip()) if isinstance(entry.get("downloads"), list) else ()
            project_url = str(failure.get("projectUrl") or (f"https://modrinth.com/project/{pack_project}" if pack_project else ""))
            version_url = str(failure.get("pageUrl") or (f"{project_url}/version/{pack_version}" if project_url and pack_version else project_url))
            requirements.append(ModrinthManualDownload(
                project_id=pack_project,
                version_id=pack_version,
                project_name=pack_name,
                file_name=Path(path).name,
                file_size=int(entry.get("size", 0) or 0),
                sha1=str(entry.get("sha1") or ""),
                sha512=str(entry.get("sha512") or ""),
                project_url=project_url,
                version_url=version_url,
                direct_url=str(failure.get("url") or (urls[0] if urls else "")),
                reason=f"Automatic download failed ({failure.get('reason') or 'UNKNOWN'}): {failure.get('detail') or 'File is missing or invalid.'}",
                failure_reason=str(failure.get("reason") or "UNKNOWN"),
                http_status=failure.get("httpStatus") if isinstance(failure.get("httpStatus"), int) else None,
                attempts=int(failure.get("attempts", 1) or 1),
                retryable=bool(failure.get("retryable", False)),
                managed_kind="pack",
                managed_path=path,
            ))
        for entry in missing_mods:
            project_id = str(entry.get("projectId") or "")
            version_id = str(entry.get("versionId") or "")
            failure = entry.get("downloadFailure") if isinstance(entry.get("downloadFailure"), dict) else {}
            urls = tuple(str(url).strip() for url in entry.get("downloadUrls", []) if str(url).strip()) if isinstance(entry.get("downloadUrls"), list) else ()
            project_url = str(failure.get("projectUrl") or (f"https://modrinth.com/project/{project_id}" if project_id else ""))
            version_url = str(failure.get("pageUrl") or (f"{project_url}/version/{version_id}" if project_url and version_id else project_url))
            requirements.append(ModrinthManualDownload(
                project_id=project_id,
                version_id=version_id,
                project_name=ModrinthContentManager._mod_title(entry),
                file_name=Path(str(entry.get("fileName") or "download.jar")).name,
                file_size=int(entry.get("size", 0) or 0),
                sha1=str(entry.get("sha1") or ""),
                sha512=str(entry.get("sha512") or ""),
                project_url=project_url,
                version_url=version_url,
                direct_url=str(failure.get("url") or (urls[0] if urls else "")),
                reason=f"Automatic download failed ({failure.get('reason') or 'UNKNOWN'}): {failure.get('detail') or entry.get('lastDownloadError') or 'File is missing or invalid.'}",
                failure_reason=str(failure.get("reason") or "UNKNOWN"),
                http_status=failure.get("httpStatus") if isinstance(failure.get("httpStatus"), int) else None,
                attempts=int(failure.get("attempts", 1) or 1),
                retryable=bool(failure.get("retryable", False)),
            ))
        return tuple(requirements)

    @staticmethod
    def _mod_key(entry: dict) -> str:
        return str(entry.get("projectId") or entry.get("versionId") or entry.get("fileName") or id(entry))

    @staticmethod
    def _mod_title(entry: dict) -> str:
        return str(entry.get("title") or entry.get("fileName") or entry.get("projectId") or "Modrinth mod")

    @staticmethod
    def _set_mod_download_state(entry: dict, pending: bool, error: str) -> bool:
        changed = bool(entry.get("pendingDownload", False)) != pending or str(entry.get("lastDownloadError") or "") != error
        entry["pendingDownload"] = pending
        entry["lastDownloadError"] = error
        return changed

    @staticmethod
    def _append_warning(warnings: list[str], warning: str) -> None:
        if warning not in warnings:
            warnings.append(warning)

    @staticmethod
    def _report_files(reporter: ProgressReporter | None, stage: ProgressStage, message: str, current: int, total: int) -> None:
        if reporter is None:
            return
        reporter.files(stage=stage, message=message, current=current, total=total)
