from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile

from src.core.atlauncher.atlauncher_pack_registry import ATLauncherPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.network.artifact_download_service import ArtifactDownloadService, artifact_download_service
from src.core.network.download_manager import download_manager
from src.core.network.download_pause import download_pause_controller
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class ATLauncherContentManager:
    """Materialize deferred ATLauncher pack files before the first launch."""

    PROGRESS_EMIT_INTERVAL_SECONDS = 0.08
    MAX_CONFIG_ENTRIES = 100_000
    MAX_CONFIG_BYTES = 10 * 1024 * 1024 * 1024

    @staticmethod
    def ensure(instance: Instance, reporter: ProgressReporter | None = None, launch_lock_token: str | None = None) -> tuple[str, ...]:
        if getattr(instance, "instance_dir", None) is None:
            return ()
        registry = ATLauncherPackRegistry.load(instance)
        if not registry:
            return ()
        ATLauncherContentManager._ensure_config_bundle(instance, registry, reporter, launch_lock_token)
        entries = [entry for entry in registry.get("managedFiles", []) if isinstance(entry, dict)]
        if not entries:
            ATLauncherPackRegistry.save(instance, registry)
            return ()
        missing = ATLauncherContentManager._missing(instance, entries, reporter)
        if not missing:
            ATLauncherPackRegistry.save(instance, registry)
            return ()
        ModManager.ensure_modifiable(instance, launch_lock_token)
        batch = FileBatchProgress(
            reporter=reporter,
            stage=ProgressStage.DOWNLOADING_MODS,
            message="Downloading ATLauncher pack files...",
            total=len(missing),
            min_emit_interval_seconds=ATLauncherContentManager.PROGRESS_EMIT_INTERVAL_SECONDS,
        )
        batch.start()
        try:
            for entry in missing:
                download_pause_controller.raise_if_requested()
                token = object()
                child_reporter = batch.reporter_for(token)
                target, relative = ArtifactDownloadService.safe_destination(Path(instance.instance_dir), str(entry.get("path") or entry.get("fileName") or ""))
                hashes: dict[str, str] = {}
                for algorithm in ("sha1", "md5"):
                    value = str(entry.get(algorithm) or "").strip().casefold()
                    if value:
                        hashes[algorithm] = value
                request = ArtifactRequest(
                    provider="atlauncher",
                    purpose="modpack-file",
                    destination=target,
                    urls=tuple(str(url).strip() for url in entry.get("urls", []) if str(url).strip()),
                    expected_filename=Path(str(entry.get("fileName") or target.name)).name,
                    expected_size=max(0, int(entry.get("size", 0) or 0)),
                    hashes=hashes,
                    project_id=str(registry.get("safeName") or registry.get("packId") or ""),
                    version_id=str(registry.get("versionName") or registry.get("versionId") or ""),
                    file_id=str(entry.get("fileId") or ""),
                    max_attempts=3,
                    max_bytes=max(0, int(entry.get("size", 0) or 0)) or 2 * 1024 * 1024 * 1024,
                )
                try:
                    artifact_download_service.download(request, reporter=child_reporter, progress_stage=ProgressStage.DOWNLOADING_MODS, progress_message="Downloading ATLauncher pack files...")
                    entry["path"] = relative
                    entry["pendingDownload"] = False
                    entry["lastDownloadError"] = ""
                except Exception as error:
                    entry["pendingDownload"] = True
                    entry["lastDownloadError"] = str(error)
                    raise RuntimeError(f"Could not download required ATLauncher file '{relative}': {error}") from error
                finally:
                    batch.complete(token)
        finally:
            ATLauncherPackRegistry.save(instance, registry)
        remaining = ATLauncherContentManager._missing(instance, entries, None)
        if remaining:
            paths = ", ".join(str(entry.get("path") or entry.get("fileName") or "unknown") for entry in remaining[:8])
            raise RuntimeError(f"Required ATLauncher pack files are still missing after download: {paths}")
        return ()

    @staticmethod
    def _ensure_config_bundle(instance: Instance, registry: dict, reporter: ProgressReporter | None, launch_lock_token: str | None) -> None:
        bundle = registry.get("configBundle")
        if not isinstance(bundle, dict) or bool(bundle.get("applied", False)):
            return
        ModManager.ensure_modifiable(instance, launch_lock_token)
        root = Path(instance.instance_dir)
        archive_path = root / ".mcw" / "atlauncher" / "Configs.zip"
        sha1 = str(bundle.get("sha1") or "").strip().casefold()
        hashes = {"sha1": sha1} if sha1 else {}
        request = ArtifactRequest(
            provider="atlauncher",
            purpose="modpack-configs",
            destination=archive_path,
            urls=(str(bundle.get("url") or "").strip(),) if str(bundle.get("url") or "").strip() else (),
            expected_filename="Configs.zip",
            expected_size=max(0, int(bundle.get("size", 0) or 0)),
            hashes=hashes,
            project_id=str(registry.get("safeName") or registry.get("packId") or ""),
            version_id=str(registry.get("versionName") or registry.get("versionId") or ""),
            max_attempts=3,
            max_bytes=max(0, int(bundle.get("size", 0) or 0)) or 4 * 1024 * 1024 * 1024,
        )
        try:
            artifact_download_service.download(request, reporter=reporter, progress_stage=ProgressStage.DOWNLOADING_MODPACK, progress_message="Downloading ATLauncher configuration files...")
            ATLauncherContentManager._safe_extract_zip(archive_path, root)
            bundle["applied"] = True
            bundle["pendingDownload"] = False
            bundle["lastDownloadError"] = ""
        except Exception as error:
            bundle["applied"] = False
            bundle["pendingDownload"] = True
            bundle["lastDownloadError"] = str(error)
            ATLauncherPackRegistry.save(instance, registry)
            raise RuntimeError(f"Could not install the ATLauncher configuration bundle: {error}") from error
        ATLauncherPackRegistry.save(instance, registry)

    @staticmethod
    def _safe_extract_zip(archive_path: Path, destination: Path) -> None:
        staging = destination / ".mcw" / "atlauncher" / "configs-staging"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        total_size = 0
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                entries = archive.infolist()
                if len(entries) > ATLauncherContentManager.MAX_CONFIG_ENTRIES:
                    raise RuntimeError("The ATLauncher configuration archive contains too many files.")
                for member in entries:
                    download_pause_controller.raise_if_requested()
                    name = member.filename.replace("\\", "/")
                    if name.endswith("/"):
                        continue
                    if stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF):
                        raise RuntimeError(f"Symbolic links are not allowed in ATLauncher configuration archives: {name}")
                    relative = ATLauncherContentManager._safe_relative(name)
                    total_size += max(0, int(member.file_size or 0))
                    if total_size > ATLauncherContentManager.MAX_CONFIG_BYTES:
                        raise RuntimeError("The ATLauncher configuration archive is larger than the safety limit.")
                    target = staging.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
            for path in staging.rglob("*"):
                if not path.is_file():
                    continue
                relative = path.relative_to(staging)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".atl.part")
                shutil.copy2(path, temporary)
                temporary.replace(target)
        except zipfile.BadZipFile as error:
            raise RuntimeError("ATLauncher returned an invalid configuration archive.") from error
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    @staticmethod
    def _safe_relative(value: str) -> PurePosixPath:
        normalized = str(value).replace("\\", "/").strip().lstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts) or ":" in path.parts[0]:
            raise RuntimeError(f"Unsafe path in ATLauncher configuration archive: {value!r}")
        if path.parts[0].casefold() in {"instance.json", "settings.json", ".mcw"}:
            raise RuntimeError(f"Reserved path in ATLauncher configuration archive: {value!r}")
        return path

    @staticmethod
    def _missing(instance: Instance, entries: list[dict], reporter: ProgressReporter | None) -> list[dict]:
        total = len(entries)
        message = "Checking ATLauncher pack files..."
        if reporter is not None:
            reporter.files(ProgressStage.CHECKING_MODS, message, 0, total)
        missing: list[dict] = []
        root = Path(instance.instance_dir)
        for index, entry in enumerate(entries, start=1):
            target, relative = ArtifactDownloadService.safe_destination(root, str(entry.get("path") or entry.get("fileName") or ""))
            hashes: dict[str, str] = {}
            for algorithm in ("sha1", "md5"):
                value = str(entry.get(algorithm) or "").strip().casefold()
                if value:
                    hashes[algorithm] = value
            valid = download_manager.verify(target, max(0, int(entry.get("size", 0) or 0)), hashes)
            entry["path"] = relative
            entry["pendingDownload"] = not valid
            if valid:
                entry["lastDownloadError"] = ""
            else:
                missing.append(entry)
            if reporter is not None and (index == total or index % 50 == 0):
                reporter.files(ProgressStage.CHECKING_MODS, message, index, total)
        return missing
