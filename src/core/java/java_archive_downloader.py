from __future__ import annotations

from pathlib import Path

from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter  # shared singleton; retained for compatibility
from src.core.network.download_manager import download_manager
from src.core.network.download_models import DownloadRequest
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.java.java_release import JavaRelease
from src.models.progress.progress_stage import ProgressStage


class JavaArchiveDownloader:
    @staticmethod
    def download(release: JavaRelease, destination: Path, reporter: ProgressReporter | None = None, max_retry: int = 3, timeout: float = 60.0) -> Path:
        request = DownloadRequest(
            urls=(release.url,),
            destination=destination,
            expected_size=max(0, int(release.size or 0)),
            hashes={"sha256": release.sha256},
            source="java",
            display_name=f"Java {release.major} archive",
            max_attempts=max_retry,
            timeout=timeout,
        )
        return download_manager.download(
            request,
            reporter=reporter,
            progress_stage=ProgressStage.DOWNLOADING_JAVA,
            progress_message=f"Downloading Java {release.major}...",
            client_provider=HttpDownloader.get_client,
        ).path

    @staticmethod
    def _download_stream(release: JavaRelease, destination: Path, reporter: ProgressReporter | None, timeout: float) -> None:
        request = DownloadRequest(
            urls=(release.url,),
            destination=destination.with_name(destination.name.removesuffix(".part")),
            expected_size=max(0, int(release.size or 0)),
            hashes={"sha256": release.sha256},
            source="java",
            display_name=f"Java {release.major} archive",
            max_attempts=1,
            timeout=timeout,
        )
        download_manager._stream(request, release.url, reporter, ProgressStage.DOWNLOADING_JAVA, f"Downloading Java {release.major}...", HttpDownloader.get_client, target_path=destination)

    @staticmethod
    def _report(reporter: ProgressReporter | None, major: int, current: int, total: int, bytes_per_second: float | None = None) -> None:
        if reporter is not None:
            reporter.bytes(stage=ProgressStage.DOWNLOADING_JAVA, message=f"Downloading Java {major}...", current=current, total=total, bytes_per_second=bytes_per_second)
