from __future__ import annotations

from pathlib import Path
import re

from src.core.curseforge.curseforge_client import CurseForgeClient
from src.core.curseforge.curseforge_downloader import CurseForgeDownloader, CurseForgeManualDownloadRequired
from src.core.curseforge.curseforge_errors import CurseForgeManagedFilesRequired
from src.core.curseforge.curseforge_pack_registry import CurseForgePackRegistry
from src.core.curseforge.curseforge_registry import CurseForgeRegistry
from src.core.fs.paths import Paths
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.network.artifact_download_service import artifact_download_service
from src.core.network.download_pause import download_pause_controller, is_download_paused
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.models.curseforge.file import CurseForgeFile
from src.models.curseforge.manual_download import CurseForgeManualDownload
from src.models.instance.instance import Instance
from src.models.progress.progress_stage import ProgressStage


class CurseForgeContentManager:
    MAX_DOWNLOAD_ROUNDS = 3
    MAX_WORKERS = 8

    @staticmethod
    def ensure(instance: Instance, reporter: ProgressReporter | None = None, block_launch_on_failure: bool = True, launch_lock_token: str | None = None) -> tuple[str, ...]:
        if getattr(instance, "instance_dir", None) is None:
            return ()
        pack = CurseForgePackRegistry.load(instance)
        registry = CurseForgeRegistry.load(instance)
        pack_entries = [entry for entry in pack.get("managedFiles", []) if isinstance(entry, dict)]
        mod_entries = [entry for entry in registry.get("mods", {}).values() if isinstance(entry, dict)]
        if not pack_entries and not mod_entries:
            return ()

        warnings: list[str] = []
        last_errors: dict[str, dict[str, object]] = {}
        summary = {
            "downloaded": 0,
            "acceptedUnverified": 0,
            "permanentFailures": 0,
            "retryableFailures": 0,
            "rounds": 0,
        }

        for round_number in range(1, CurseForgeContentManager.MAX_DOWNLOAD_ROUNDS + 1):
            missing = CurseForgeContentManager._check_all(instance, pack_entries, mod_entries, reporter, round_number)
            if not missing:
                CurseForgeContentManager._save_success(pack, registry, instance, summary)
                CurseForgeContentManager._report_summary(reporter, len(pack_entries) + len(mod_entries), summary)
                if summary["acceptedUnverified"]:
                    warnings.append(
                        f"Installed {summary['acceptedUnverified']} CurseForge file(s) with unverified loader compatibility because they were declared by the modpack."
                    )
                return tuple(warnings)

            retryable = [item for item in missing if bool(item["entry"].get("retryableDownload", True))]
            if not retryable:
                break

            ModManager.ensure_modifiable(instance, launch_lock_token)
            round_result = CurseForgeContentManager._download_round(instance, retryable, reporter, round_number, launch_lock_token)
            summary["rounds"] = round_number
            summary["downloaded"] += int(round_result["downloaded"])
            summary["acceptedUnverified"] += int(round_result["acceptedUnverified"])
            last_errors.update(round_result["errors"])

            if pack:
                pack["lastDownloadFailures"] = [
                    {
                        "projectId": int(item["entry"].get("projectId") or 0),
                        "fileId": int(item["entry"].get("fileId") or 0),
                        "fileName": str(item["entry"].get("fileName") or Path(item["path"]).name),
                        "path": item["path"],
                        "error": str(round_result["errors"].get(item["key"], {}).get("message") or "Download failed"),
                        "retryable": bool(round_result["errors"].get(item["key"], {}).get("retryable", True)),
                    }
                    for item in retryable
                    if item["kind"] == "pack" and item["key"] in round_result["errors"]
                ]
                pack["lastDownloadSummary"] = dict(summary)
                CurseForgePackRegistry.save(instance, pack)
            CurseForgeRegistry.save(instance, registry)

            if not any(bool(error.get("retryable", True)) for error in round_result["errors"].values()):
                break

        missing = CurseForgeContentManager._check_all(instance, pack_entries, mod_entries, reporter, CurseForgeContentManager.MAX_DOWNLOAD_ROUNDS + 1)
        if not missing:
            CurseForgeContentManager._save_success(pack, registry, instance, summary)
            CurseForgeContentManager._report_summary(reporter, len(pack_entries) + len(mod_entries), summary)
            if summary["acceptedUnverified"]:
                warnings.append(
                    f"Installed {summary['acceptedUnverified']} CurseForge file(s) with unverified loader compatibility because they were declared by the modpack."
                )
            return tuple(warnings)

        permanent = [item for item in missing if not bool(item["entry"].get("retryableDownload", True))]
        retryable = [item for item in missing if bool(item["entry"].get("retryableDownload", True))]
        summary["permanentFailures"] = len(permanent)
        summary["retryableFailures"] = len(retryable)
        if pack:
            pack["lastDownloadSummary"] = dict(summary)
            CurseForgePackRegistry.save(instance, pack)
        CurseForgeRegistry.save(instance, registry)

        message = CurseForgeContentManager._failure_message(missing, last_errors)
        requirements = CurseForgeContentManager._manual_requirements(missing, last_errors)
        if block_launch_on_failure:
            if requirements:
                raise CurseForgeManagedFilesRequired(instance, requirements, message)
            raise RuntimeError(message)
        warnings.append(message)
        return tuple(warnings)

    @staticmethod
    def _save_success(pack: dict, registry: dict, instance: Instance, summary: dict[str, int]) -> None:
        if pack:
            pack["lastDownloadFailures"] = []
            pack["lastDownloadSummary"] = dict(summary)
            CurseForgePackRegistry.save(instance, pack)
        CurseForgeRegistry.save(instance, registry)

    @staticmethod
    def _report_summary(reporter: ProgressReporter | None, total: int, summary: dict[str, int]) -> None:
        if reporter is None:
            return
        message = (
            "CurseForge files ready: "
            f"{summary['downloaded']} downloaded, "
            f"{summary['acceptedUnverified']} accepted with compatibility warnings."
        )
        reporter.files(stage=ProgressStage.CHECKING_MODS, message=message, current=total, total=total)

    @staticmethod
    def _check_all(instance: Instance, pack_entries: list[dict], mod_entries: list[dict], reporter: ProgressReporter | None, round_number: int) -> list[dict]:
        combined: list[dict] = []
        for entry in pack_entries:
            combined.append(CurseForgeContentManager._item(entry, "pack"))
        for entry in mod_entries:
            combined.append(CurseForgeContentManager._item(entry, "mod"))
        total = len(combined)
        missing: list[dict] = []
        message = "Checking CurseForge files..." if round_number == 1 else f"Checking CurseForge files after round {min(round_number - 1, 3)}/3..."
        if reporter is not None:
            reporter.files(stage=ProgressStage.CHECKING_MODS, message=message, current=0, total=total)
        for index, item in enumerate(combined, start=1):
            path = Path(instance.instance_dir) / item["path"]
            valid = path.is_file() and CurseForgeContentManager._verify(path, item["sha1"], item["size"])
            item["entry"]["pendingDownload"] = not valid
            if valid:
                item["entry"]["lastDownloadError"] = ""
                item["entry"]["retryableDownload"] = True
            else:
                item["entry"]["lastDownloadError"] = str(item["entry"].get("lastDownloadError") or "File is missing or invalid")
                missing.append(item)
            if reporter is not None and (index == total or index % 50 == 0):
                reporter.files(stage=ProgressStage.CHECKING_MODS, message=message, current=index, total=total)
        return missing

    @staticmethod
    def _download_round(instance: Instance, missing: list[dict], reporter: ProgressReporter | None, round_number: int, launch_lock_token: str | None = None) -> dict[str, object]:
        errors: dict[str, dict[str, object]] = {}
        downloaded = 0
        accepted_unverified = 0
        message = "Downloading modpack mods..."
        batch_progress = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_MODS, message=message, total=len(missing), min_emit_interval_seconds=0.08)
        batch_progress.start()

        for item in missing:
            download_pause_controller.raise_if_requested()
            token = object()
            child_reporter = batch_progress.reporter_for(token)
            entry = item["entry"]
            try:
                file = CurseForgeContentManager._file_from_entry(entry)
                if not file.file_name or not file.sha1:
                    file = CurseForgeClient.get_file(file.project_id, file.file_id, force_refresh=True)
                cache = Paths.curseforge_file_cache(file.project_id, file.file_id, file.file_name)
                CurseForgeDownloader.download_file(
                    file,
                    cache,
                    reporter=child_reporter,
                    project_name="Modpack mod",
                    purpose="modpack-artifact" if item["kind"] == "pack" else "mod",
                    managed_kind=str(item["kind"]),
                    managed_path=str(item["path"]),
                    project_url=str(entry.get("projectUrl") or entry.get("project_url") or ""),
                )
                download_pause_controller.raise_if_requested()

                compatibility_warning = ""
                if item["kind"] == "pack":
                    requested_path = "" if bool(entry.get("resolvePathFromProvider", False)) else str(item["path"])
                    target, relative = CurseForgePackRegistry.managed_path(instance, requested_path, file.file_name)
                    request = CurseForgeContentManager._artifact_request(file, target, item)
                    artifact_download_service.accept_manual_file(request, cache)
                    entry["fileName"] = target.name
                    entry["path"] = relative
                    if target.suffix.casefold() == ".jar":
                        loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
                        metadata = ModManager.read_mod(target, preferred_loader=loader_name, provider_version=file.display_name)
                        compatibility_warning = ModManager.compatibility_warning(instance, metadata)
                else:
                    loader_name, _ = ModLoaderManager.normalize(instance.mod_loader)
                    metadata = ModManager.read_mod(cache, preferred_loader=loader_name, provider_version=file.display_name)
                    compatibility_warning = ModManager.compatibility_warning(instance, metadata)
                    added = ModManager.add_mods(instance, [cache], replace=True, launch_lock_token=launch_lock_token, allow_unverified=True)
                    if not added:
                        raise RuntimeError("Downloaded file could not be added to the instance.")
                    entry["fileName"] = added[0].file_name
                    entry["path"] = f"mods/{added[0].file_name}"

                entry["sha1"] = file.sha1 or str(entry.get("sha1") or "")
                entry["size"] = file.file_length or int(entry.get("size", 0) or 0)
                entry["downloadUrl"] = file.download_url or str(entry.get("downloadUrl") or "")
                entry["pendingDownload"] = False
                entry["lastDownloadError"] = ""
                entry["retryableDownload"] = True
                entry["acceptedUnverified"] = bool(compatibility_warning)
                entry["compatibilityWarning"] = compatibility_warning
                entry["resolvePathFromProvider"] = False
                downloaded += 1
                accepted_unverified += int(bool(compatibility_warning))
            except Exception as error:
                if is_download_paused(error):
                    raise
                retryable = not isinstance(error, CurseForgeManualDownloadRequired) and not CurseForgeClient.is_permanent_error(error)
                entry["pendingDownload"] = True
                entry["lastDownloadError"] = str(error)
                entry["retryableDownload"] = retryable
                error_payload: dict[str, object] = {"message": str(error), "retryable": retryable}
                if isinstance(error, CurseForgeManualDownloadRequired):
                    requirement = error.requirement
                    error_payload["requirement"] = CurseForgeManualDownload(
                        project_id=requirement.project_id,
                        file_id=requirement.file_id,
                        project_name=str(entry.get("displayName") or requirement.project_name),
                        file_name=requirement.file_name,
                        file_size=requirement.file_size,
                        sha1=requirement.sha1,
                        project_url=requirement.project_url,
                        reason=requirement.reason,
                        managed_kind=str(item.get("kind") or "mod"),
                        managed_path=str(item.get("path") or ""),
                        direct_url=requirement.direct_url,
                        version_url=requirement.version_url,
                        failure_reason=requirement.failure_reason,
                        http_status=requirement.http_status,
                        attempts=requirement.attempts,
                        retryable=requirement.retryable,
                    )
                errors[item["key"]] = error_payload
            finally:
                batch_progress.complete(token)
        return {"errors": errors, "downloaded": downloaded, "acceptedUnverified": accepted_unverified}

    @staticmethod
    def _artifact_request(file: CurseForgeFile, destination: Path, item: dict):
        from src.models.network.artifact import ArtifactRequest
        return ArtifactRequest(
            provider="curseforge",
            purpose="modpack-artifact",
            destination=destination,
            urls=(file.download_url,) if file.download_url else (),
            expected_filename=Path(str(item.get("path") or file.file_name)).name,
            expected_size=file.file_length,
            hashes={"sha1": file.sha1} if file.sha1 else {},
            project_id=str(file.project_id),
            file_id=str(file.file_id),
        )

    @staticmethod
    def _file_from_entry(entry: dict) -> CurseForgeFile:
        return CurseForgeFile(
            file_id=int(entry.get("fileId") or 0),
            project_id=int(entry.get("projectId") or 0),
            display_name=str(entry.get("displayName") or entry.get("fileName") or "Unknown file").strip(),
            file_name=Path(str(entry.get("fileName") or "download.bin")).name,
            release_type=str(entry.get("releaseType") or "release").strip().lower(),
            file_date=str(entry.get("datePublished") or "").strip(),
            file_length=max(0, int(entry.get("size", 0) or 0)),
            download_url=str(entry.get("downloadUrl") or "").strip(),
            sha1=str(entry.get("sha1") or "").strip().lower(),
            game_versions=tuple(str(value) for value in entry.get("gameVersions", []) if str(value).strip()),
            dependencies=(),
            is_available=bool(entry.get("isAvailable", True)),
            loaders=tuple(str(value).strip().lower() for value in entry.get("declaredLoaders", []) if str(value).strip()),
        )

    @staticmethod
    def _manual_requirements(missing: list[dict], last_errors: dict[str, dict[str, object]]) -> tuple[CurseForgeManualDownload, ...]:
        project_ids = {int(item["entry"].get("projectId") or 0) for item in missing if int(item["entry"].get("projectId") or 0) > 0}
        try:
            projects = CurseForgeClient.get_projects_batch(project_ids) if project_ids else {}
        except Exception:
            projects = {}

        requirements: list[CurseForgeManualDownload] = []
        seen: set[tuple[int, int, str]] = set()
        for item in missing:
            entry = item["entry"]
            project_id = int(entry.get("projectId") or 0)
            file_id = int(entry.get("fileId") or 0)
            key = (project_id, file_id, str(item.get("path") or ""))
            if project_id <= 0 or file_id <= 0 or key in seen:
                continue
            seen.add(key)

            error_payload = last_errors.get(item["key"], {})
            existing = error_payload.get("requirement")
            project = projects.get(project_id)
            project_name = str(getattr(project, "name", "") or entry.get("displayName") or entry.get("fileName") or f"CurseForge project {project_id}").strip()
            project_url = str(getattr(project, "project_url", "") or getattr(existing, "project_url", "") or "").rstrip("/")
            if not project_url:
                project_url = f"https://www.curseforge.com/minecraft/mc-mods/{project_id}"
            version_url = str(getattr(existing, "version_url", "") or "").strip()
            if not version_url and project_url and file_id > 0:
                version_url = f"{project_url}/files/{file_id}"
            raw_reason = str(error_payload.get("message") or entry.get("lastDownloadError") or "File is missing or invalid")
            reason = str(getattr(existing, "reason", "") or CurseForgeContentManager._normalized_error(raw_reason))
            requirements.append(
                CurseForgeManualDownload(
                    project_id=project_id,
                    file_id=file_id,
                    project_name=project_name,
                    file_name=Path(str(entry.get("fileName") or getattr(existing, "file_name", "download.jar"))).name,
                    file_size=max(0, int(entry.get("size", 0) or getattr(existing, "file_size", 0) or 0)),
                    sha1=str(entry.get("sha1") or getattr(existing, "sha1", "")).strip().lower(),
                    project_url=project_url,
                    reason=reason,
                    managed_kind=str(item.get("kind") or "mod"),
                    managed_path=str(item.get("path") or ""),
                    direct_url=str(getattr(existing, "direct_url", "") or entry.get("downloadUrl") or "").strip(),
                    version_url=version_url,
                    failure_reason=str(getattr(existing, "failure_reason", "") or "UNKNOWN"),
                    http_status=getattr(existing, "http_status", None),
                    attempts=max(1, int(getattr(existing, "attempts", 1) or 1)),
                    retryable=bool(getattr(existing, "retryable", False)),
                )
            )
        return tuple(requirements)

    @staticmethod
    def _failure_message(missing: list[dict], last_errors: dict[str, dict[str, object]]) -> str:
        groups: dict[str, list[str]] = {}
        for item in missing:
            raw = str(last_errors.get(item["key"], {}).get("message") or item["entry"].get("lastDownloadError") or "File is still missing or invalid")
            key = CurseForgeContentManager._normalized_error(raw)
            groups.setdefault(key, []).append(item["path"])

        lines = ["Required CurseForge files are still missing:"]
        for error, paths in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0].casefold())):
            sample = ", ".join(paths[:3])
            if len(paths) > 3:
                sample += f", and {len(paths) - 3} more"
            lines.append(f"- {len(paths)} file(s): {error} [{sample}]")
        return "\n".join(lines)

    @staticmethod
    def _normalized_error(message: str) -> str:
        value = str(message).strip()
        normalized = value.casefold()
        if "credentials are unavailable" in normalized or "gateway credentials" in normalized:
            return "The CurseForge gateway credentials were rejected. Check the gateway deployment and API-key configuration."
        if "must be downloaded manually" in normalized or "manual download required" in normalized or "third-party distribution" in normalized:
            return "Manual download is required because CurseForge does not permit third-party distribution for these files."
        value = re.sub(r"\s*Request ID:\s*[0-9a-f-]+\.?", "", value, flags=re.IGNORECASE)
        return value or "File is still missing or invalid"

    @staticmethod
    def _item(entry: dict, kind: str) -> dict:
        filename = Path(str(entry.get("fileName") or "")).name
        raw_path = str(entry.get("path") or f"mods/{filename}")
        path = CurseForgePackRegistry.safe_relative_path(raw_path, filename)
        key = f"{kind}:{entry.get('projectId')}:{entry.get('fileId')}"
        return {"kind": kind, "key": key, "path": path, "sha1": str(entry.get("sha1") or "").lower(), "size": max(0, int(entry.get("size", 0) or 0)), "entry": entry}

    @staticmethod
    def _verify(path: Path, sha1: str, size: int) -> bool:
        try:
            if size > 0 and path.stat().st_size != size:
                return False
        except OSError:
            return False
        if sha1:
            from src.core.network.httpx_downloader import HttpDownloader
            return HttpDownloader.verify_sha1(path, sha1)
        return path.is_file()
