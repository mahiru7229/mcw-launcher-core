from __future__ import annotations

from pathlib import Path
import zipfile
from src.core.fs.paths import Paths
from src.core.instance.instance_manager import InstanceManager
from src.core.network.artifact_download_service import ArtifactDownloadError, artifact_download_service
from src.core.network.download_pause import DownloadCancelledError
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.network.artifact import ArtifactRequest
from src.models.progress.progress_stage import ProgressStage


class InstanceArtworkManager:
    MAX_ARTWORK_BYTES = InstanceManager.MAX_ICON_BYTES
    EMBEDDED_ICON_NAMES = frozenset(
        f"{prefix}{extension}"
        for prefix in ("mcw/instance-icon", ".mcw/instance-icon", "overrides/.mcw/instance-icon", "overrides/mcw/instance-icon")
        for extension in InstanceManager.ICON_EXTENSIONS
    )

    @classmethod
    def has_custom_artwork(cls, instance: Instance) -> bool:
        return InstanceManager.resolve_icon_path(instance) is not None

    @classmethod
    def apply_embedded_archive_artwork(cls, instance: Instance, archive: zipfile.ZipFile) -> bool:
        """Restore a known embedded instance icon without trusting arbitrary paths."""
        candidates = []
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/").strip("/").casefold()
            if normalized not in cls.EMBEDDED_ICON_NAMES or info.is_dir():
                continue
            if info.file_size <= 0 or info.file_size > cls.MAX_ARTWORK_BYTES:
                continue
            candidates.append((normalized, info))
        if not candidates:
            return False
        _name, info = sorted(candidates, key=lambda item: item[0])[0]
        try:
            data = archive.read(info)
            extension = cls._detect_extension_bytes(data[:16])
            icon_dir = Path(instance.instance_dir) / InstanceManager.ICON_DIRECTORY
            icon_dir.mkdir(parents=True, exist_ok=True)
            source = icon_dir / f".provider-embedded-icon{extension}"
            source.write_bytes(data)
            try:
                InstanceManager.set_icon(instance.name, source, origin={"provider": "embedded", "member": info.filename})
            finally:
                source.unlink(missing_ok=True)
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile):
            return False
        return True

    @classmethod
    def apply_provider_artwork(cls, instance: Instance, provider: str, project_id: object, artwork_url: str, reporter: ProgressReporter | None = None) -> bool:
        url = str(artwork_url or "").strip()
        normalized_provider = str(provider or "provider").strip().casefold() or "provider"
        normalized_project = str(project_id or "unknown").strip() or "unknown"
        if not url:
            return False

        cache_base = Paths.instance_artwork_cache(normalized_provider, normalized_project, url)
        cached = cls._existing_cached_artwork(cache_base)
        if cached is None:
            download_path = cache_base.with_suffix(".download")
            request = ArtifactRequest(
                provider=normalized_provider,
                purpose="instance-artwork",
                destination=download_path,
                urls=(url,),
                expected_filename="instance-artwork",
                project_id=normalized_project,
                allow_unverified=True,
                max_bytes=cls.MAX_ARTWORK_BYTES,
                max_attempts=2,
            )
            try:
                artifact_download_service.download(
                    request,
                    reporter=reporter,
                    progress_stage=ProgressStage.DOWNLOADING_MODPACK,
                    progress_message="Downloading modpack artwork...",
                )
                extension = cls._detect_extension(download_path)
                cached = cache_base.with_suffix(extension)
                cached.parent.mkdir(parents=True, exist_ok=True)
                download_path.replace(cached)
            except DownloadCancelledError:
                download_path.unlink(missing_ok=True)
                raise
            except (ArtifactDownloadError, OSError, RuntimeError, ValueError):
                download_path.unlink(missing_ok=True)
                return False

        try:
            InstanceManager.set_icon(
                instance.name,
                cached,
                origin={"provider": normalized_provider, "project_id": normalized_project},
            )
        except (OSError, RuntimeError, ValueError):
            return False
        return True

    @classmethod
    def _existing_cached_artwork(cls, cache_base: Path) -> Path | None:
        for extension in sorted(InstanceManager.ICON_EXTENSIONS):
            candidate = cache_base.with_suffix(extension)
            if not candidate.is_file():
                continue
            try:
                detected = cls._detect_extension(candidate)
                suffix_matches = detected == extension or {detected, extension} <= {".jpg", ".jpeg"}
                if 0 < candidate.stat().st_size <= cls.MAX_ARTWORK_BYTES and suffix_matches:
                    return candidate
            except (OSError, RuntimeError):
                continue
        return None

    @staticmethod
    def _detect_extension(path: Path) -> str:
        return InstanceArtworkManager._detect_extension_bytes(path.read_bytes()[:16])

    @staticmethod
    def _detect_extension_bytes(data: bytes) -> str:
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        if data.startswith(b"BM"):
            return ".bmp"
        if data.startswith(b"\x00\x00\x01\x00"):
            return ".ico"
        raise RuntimeError("The provider artwork is not a supported image.")
