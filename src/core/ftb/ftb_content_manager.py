from __future__ import annotations

from pathlib import Path

from src.core.ftb.ftb_pack_registry import FTBPackRegistry
from src.core.mod.mod_manager import ModManager
from src.core.network.artifact_download_service import ArtifactDownloadService, artifact_download_service
from src.core.network.download_manager import download_manager
from src.core.network.download_pause import download_pause_controller
from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class FTBContentManager:
    """Materialize deferred FTB modpack files immediately before launch."""

    PROGRESS_EMIT_INTERVAL_SECONDS = 0.08

    @staticmethod
    def ensure(instance: Instance, reporter: ProgressReporter | None = None, launch_lock_token: str | None = None) -> tuple[str, ...]:
        if getattr(instance, "instance_dir", None) is None:
            return ()
        registry = FTBPackRegistry.load(instance)
        entries = [entry for entry in registry.get("managedFiles", []) if isinstance(entry, dict)]
        if not entries:
            return ()

        missing = FTBContentManager._missing(instance, entries, reporter)
        if not missing:
            return ()

        ModManager.ensure_modifiable(instance, launch_lock_token)
        total = len(missing)
        batch = FileBatchProgress(
            reporter=reporter,
            stage=ProgressStage.DOWNLOADING_MODS,
            message="Downloading modpack mods...",
            total=total,
            min_emit_interval_seconds=FTBContentManager.PROGRESS_EMIT_INTERVAL_SECONDS,
        )
        batch.start()

        try:
            for entry in missing:
                download_pause_controller.raise_if_requested()
                token = object()
                child_reporter = batch.reporter_for(token)
                target, relative = ArtifactDownloadService.safe_destination(Path(instance.instance_dir), str(entry.get("path") or entry.get("fileName") or ""))
                request = ArtifactRequest(
                    provider="ftb",
                    purpose="modpack-file",
                    destination=target,
                    urls=tuple(str(url).strip() for url in entry.get("urls", []) if str(url).strip()),
                    expected_filename=Path(str(entry.get("fileName") or target.name)).name,
                    expected_size=max(0, int(entry.get("size", 0) or 0)),
                    hashes={"sha1": str(entry.get("sha1") or "").strip().casefold()} if str(entry.get("sha1") or "").strip() else {},
                    project_id=str(registry.get("projectId") or ""),
                    version_id=str(registry.get("versionId") or ""),
                    file_id=str(entry.get("fileId") or ""),
                    max_attempts=3,
                    max_bytes=max(0, int(entry.get("size", 0) or 0)) or 2 * 1024 * 1024 * 1024,
                )
                try:
                    artifact_download_service.download(
                        request,
                        reporter=child_reporter,
                        progress_stage=ProgressStage.DOWNLOADING_MODS,
                        progress_message="Downloading modpack mods...",
                    )
                    entry["path"] = relative
                    entry["pendingDownload"] = False
                    entry["lastDownloadError"] = ""
                except Exception as error:
                    entry["pendingDownload"] = True
                    entry["lastDownloadError"] = str(error)
                    raise RuntimeError(f"Could not download required FTB file '{relative}': {error}") from error
                finally:
                    batch.complete(token)
        finally:
            FTBPackRegistry.save(instance, registry)

        remaining = FTBContentManager._missing(instance, entries, None)
        if remaining:
            paths = ", ".join(str(entry.get("path") or entry.get("fileName") or "unknown") for entry in remaining[:8])
            raise RuntimeError(f"Required FTB modpack files are still missing after download: {paths}")
        return ()

    @staticmethod
    def _missing(instance: Instance, entries: list[dict], reporter: ProgressReporter | None) -> list[dict]:
        total = len(entries)
        message = "Checking modpack mods..."
        if reporter is not None:
            reporter.files(ProgressStage.CHECKING_MODS, message, 0, total)
        missing: list[dict] = []
        root = Path(instance.instance_dir)
        for index, entry in enumerate(entries, start=1):
            target, relative = ArtifactDownloadService.safe_destination(root, str(entry.get("path") or entry.get("fileName") or ""))
            hashes = {"sha1": str(entry.get("sha1") or "").strip().casefold()} if str(entry.get("sha1") or "").strip() else {}
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
