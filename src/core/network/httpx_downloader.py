from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from threading import Lock
from typing import Protocol
import time

import httpx

from src.core.network.download_manager import CHUNK_SIZE, CONTENT_RANGE_PATTERN, download_manager
from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter  # shared singleton; compatibility export
from src.core.network.download_journal import download_journal
from src.core.network.download_models import DownloadRequest, DownloadState
from src.core.network.download_pause import DownloadCancelledError, DownloadPausedError, download_pause_controller
from src.core.network.network_errors import DownloadChecksumMismatchError, DownloadFailedError
from src.core.network.network_session import network_session
from src.core.network.retry_policy import DownloadRetryPolicy
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


class DownloadInfo(Protocol):
    url: str
    sha1: str
    size: int


@dataclass(frozen=True)
class _DirectDownloadInfo:
    url: str
    size: int = 0
    sha1: str = ""


class HttpDownloader:
    """Compatibility facade for the unified v0.9 download engine.

    Existing managers keep their stable API while downloads are coordinated by
    DownloadManager, NetworkSession, DownloadRetryPolicy, and DownloadJournal.
    """

    RETRYABLE_STATUS_CODES = DownloadRetryPolicy.RETRYABLE_STATUS_CODES
    CONTENT_RANGE_PATTERN = CONTENT_RANGE_PATTERN

    _client: httpx.Client | None = None
    _client_lock = Lock()
    _path_locks = download_manager._path_locks
    _path_locks_guard = download_manager._lock

    @classmethod
    def get_client(cls) -> httpx.Client:
        with cls._client_lock:
            if cls._client is not None and not cls._client.is_closed:
                return cls._client
            cls._client = network_session.get_client()
            return cls._client

    @classmethod
    def close_client(cls) -> None:
        with cls._client_lock:
            if cls._client is not None and not cls._client.is_closed:
                cls._client.close()
            network_session.close()
            cls._client = None

    @classmethod
    def _get_path_lock(cls, path: Path):
        return download_manager.get_path_lock(path)

    @staticmethod
    def download(download_info: DownloadInfo, path: Path, max_retry: int = 2, timeout: float = 20.0, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None) -> Path:
        if max_retry < 1:
            raise ValueError("max_retry must be at least 1")
        download_pause_controller.raise_if_requested()
        path_lock = HttpDownloader._get_path_lock(path)
        with path_lock:
            return HttpDownloader._download_and_verify(download_info=download_info, path=path, max_retry=max_retry, timeout=timeout, reporter=reporter, progress_stage=progress_stage, progress_message=progress_message)

    @staticmethod
    def _download_stream(download_info: DownloadInfo, path: Path, timeout: float, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None) -> None:
        request = DownloadRequest(
            urls=(str(download_info.url),),
            destination=path.with_name(path.name[:-5]) if path.name.endswith(".part") else path,
            expected_size=max(0, int(getattr(download_info, "size", 0) or 0)),
            hashes={"sha1": str(getattr(download_info, "sha1", "") or "")},
            source="legacy-stream",
            display_name=path.name.removesuffix(".part"),
            max_attempts=1,
            timeout=timeout,
        )
        if request.temporary_path != path:
            request = DownloadRequest(
                urls=request.urls,
                destination=path.with_name(path.name.removesuffix(".part")),
                expected_size=request.expected_size,
                hashes=request.hashes,
                source=request.source,
                display_name=request.display_name,
                max_attempts=1,
                timeout=timeout,
                request_id=request.request_id,
            )
        host = (urlsplit(request.urls[0]).hostname or "unknown").casefold()
        with download_manager._slot(host):
            download_manager._stream(request, request.urls[0], reporter, progress_stage, progress_message, HttpDownloader.get_client, target_path=path)

    @staticmethod
    def _report_progress(reporter: ProgressReporter | None, stage: ProgressStage | None, message: str | None, current: int, total: int, bytes_per_second: float | None = None) -> None:
        download_manager._report(reporter, stage, message, current, total, bytes_per_second)

    @staticmethod
    def calculate_sha1(path: Path) -> str | None:
        if not Path(path).is_file():
            return None
        try:
            return download_manager.calculate_hash(Path(path), "sha1")
        except OSError:
            return None

    @staticmethod
    def verify_sha1(path: Path, expected_sha1: str) -> bool:
        if not expected_sha1:
            return False
        return download_manager.verify(Path(path), 0, {"sha1": expected_sha1})

    @staticmethod
    def download_and_hash(url: str, path: Path, max_retry: int = 2, timeout: float = 20.0, force: bool = False, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None) -> tuple[Path, str, int]:
        if max_retry < 1:
            raise ValueError("max_retry must be at least 1")
        return download_manager.download_and_hash(url=url, path=path, max_attempts=max_retry, timeout=timeout, force=force, reporter=reporter, progress_stage=progress_stage, progress_message=progress_message, client_provider=HttpDownloader.get_client)

    @staticmethod
    def _content_length(response: httpx.Response, fallback: int) -> int:
        return download_manager.content_length(response, fallback)

    @staticmethod
    def _parse_content_range(response: httpx.Response) -> tuple[int, int, int | None] | None:
        return download_manager.parse_content_range(response)

    @staticmethod
    def _valid_content_range(response: httpx.Response, expected_start: int, expected_size: int) -> bool:
        return download_manager.valid_content_range(response, expected_start, expected_size)

    @staticmethod
    def _content_range_total(response: httpx.Response) -> int:
        return download_manager.content_range_total(response)

    @staticmethod
    def _partial_size(path: Path, expected_size: int) -> int:
        return download_manager.partial_size(path, expected_size)

    @staticmethod
    def _error_response(error: Exception | None) -> httpx.Response | None:
        return DownloadRetryPolicy.response_for(error)

    @staticmethod
    def _should_retry(error: Exception, attempt: int, max_retry: int) -> bool:
        return DownloadRetryPolicy.decide(error, attempt, max_retry).retry

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
        return DownloadRetryPolicy.retry_delay(attempt, response)

    @staticmethod
    def _sleep_retry(seconds: float) -> None:
        if download_pause_controller.is_active:
            download_pause_controller.wait(seconds)
        else:
            time.sleep(seconds)

    @staticmethod
    def _describe_error(error: Exception | None) -> str:
        return download_manager.describe_error(error)

    @staticmethod
    def delete_file(path: Path) -> None:
        download_manager.delete_file(path)

    @staticmethod
    def _download_and_verify(download_info: DownloadInfo, path: Path, max_retry: int, timeout: float, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None) -> Path:
        if max_retry < 1:
            raise ValueError("max_retry must be at least 1")
        if HttpDownloader.verify_sha1(path, download_info.sha1):
            return path

        temp_path = path.with_name(f"{path.name}.part")
        if HttpDownloader.verify_sha1(temp_path, download_info.sha1):
            temp_path.replace(path)
            return path

        request = DownloadRequest(
            urls=(str(download_info.url),),
            destination=Path(path),
            expected_size=max(0, int(getattr(download_info, "size", 0) or 0)),
            hashes={"sha1": str(getattr(download_info, "sha1", "") or "")},
            source="http",
            display_name=Path(path).name,
            max_attempts=max_retry,
            timeout=timeout,
        )
        last_error: Exception | None = None
        for attempt in range(1, max_retry + 1):
            download_pause_controller.raise_if_requested()
            try:
                HttpDownloader._download_stream(
                    download_info=download_info,
                    path=temp_path,
                    timeout=timeout,
                    reporter=reporter,
                    progress_stage=progress_stage,
                    progress_message=progress_message,
                )
                if not HttpDownloader.verify_sha1(temp_path, download_info.sha1):
                    HttpDownloader.delete_file(temp_path)
                    raise DownloadChecksumMismatchError(path.name, "sha1")
                temp_path.replace(path)
                download_journal.complete(request, path.stat().st_size)
                return path
            except DownloadCancelledError as error:
                downloaded = download_manager._safe_size(temp_path)
                HttpDownloader.delete_file(temp_path)
                download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(error))
                raise
            except DownloadPausedError as error:
                download_journal.update(request, DownloadState.PAUSED, downloaded_bytes=download_manager._safe_size(temp_path), error=str(error))
                raise
            except (httpx.HTTPError, OSError, RuntimeError) as error:
                last_error = error
                decision = DownloadRetryPolicy.decide(error, attempt, max_retry)
                if not decision.preserve_partial:
                    HttpDownloader.delete_file(temp_path)
                download_journal.update(request, DownloadState.FAILED, downloaded_bytes=download_manager._safe_size(temp_path), error=str(error))
                if not decision.retry:
                    break
                try:
                    HttpDownloader._sleep_retry(decision.delay_seconds)
                except DownloadCancelledError as cancelled:
                    downloaded = download_manager._safe_size(temp_path)
                    HttpDownloader.delete_file(temp_path)
                    download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(cancelled))
                    raise

        reason = HttpDownloader._describe_error(last_error)
        download_journal.update(request, DownloadState.FAILED, downloaded_bytes=download_manager._safe_size(temp_path), error=reason)
        raise DownloadFailedError(path.name, max_retry, reason, url=str(download_info.url)) from last_error
