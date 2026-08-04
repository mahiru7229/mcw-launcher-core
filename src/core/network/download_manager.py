from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore, RLock
from time import monotonic
from urllib.parse import urlsplit
import hashlib
import re

import httpx

from src.core.network.download_bandwidth_limiter import download_bandwidth_limiter
from src.core.network.download_journal import download_journal
from src.core.network.download_models import DownloadRequest, DownloadResult, DownloadState
from src.core.network.download_pause import DownloadCancelledError, DownloadPausedError, download_pause_controller
from src.core.network.network_errors import DownloadChecksumMismatchError, DownloadFailedError, DownloadSizeMismatchError, DownloadValidationError
from src.core.network.network_session import DEFAULT_MAX_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS, network_session
from src.core.network.retry_policy import DownloadRetryPolicy
from src.core.progress.download_rate_meter import DownloadRateMeter
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


CHUNK_SIZE = 1024 * 1024
DEFAULT_PER_HOST_LIMIT = 8
CONTENT_RANGE_PATTERN = re.compile(r"^bytes\s+(\d+)-(\d+)/(\d+|\*)$", re.IGNORECASE)


class DownloadManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._global_limit = network_session.max_concurrent_downloads
        self._per_host_limit = min(DEFAULT_PER_HOST_LIMIT, self._global_limit)
        self._global_semaphore = BoundedSemaphore(self._global_limit)
        self._host_semaphores: dict[str, BoundedSemaphore] = defaultdict(lambda: BoundedSemaphore(self._per_host_limit))
        self._path_locks: dict[Path, RLock] = {}

    @property
    def max_concurrent_downloads(self) -> int:
        with self._lock:
            return self._global_limit

    @property
    def per_host_limit(self) -> int:
        with self._lock:
            return self._per_host_limit

    def configure(self, max_concurrent_downloads: object = DEFAULT_MAX_CONCURRENT_DOWNLOADS, per_host_limit: object | None = None) -> tuple[int, int]:
        try:
            total = int(max_concurrent_downloads)
        except (TypeError, ValueError):
            total = DEFAULT_MAX_CONCURRENT_DOWNLOADS
        total = min(max(total, 1), MAX_CONCURRENT_DOWNLOADS)
        if per_host_limit is None:
            per_host = min(DEFAULT_PER_HOST_LIMIT, total)
        else:
            try:
                per_host = int(per_host_limit)
            except (TypeError, ValueError):
                per_host = min(DEFAULT_PER_HOST_LIMIT, total)
        per_host = min(max(per_host, 1), total)
        with self._lock:
            if total != self._global_limit or per_host != self._per_host_limit:
                self._global_limit = total
                self._per_host_limit = per_host
                self._global_semaphore = BoundedSemaphore(total)
                self._host_semaphores = defaultdict(lambda: BoundedSemaphore(per_host))
            network_session.configure(total)
        return total, per_host

    def get_path_lock(self, path: Path) -> RLock:
        try:
            normalized = Path(path).resolve(strict=False)
        except OSError:
            normalized = Path(path).absolute()
        with self._lock:
            return self._path_locks.setdefault(normalized, RLock())

    def download(self, request: DownloadRequest, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider=None) -> DownloadResult:
        if not request.urls:
            raise DownloadValidationError(f"No download URL is available for '{request.display_name}'.")
        if not request.hashes and not request.allow_unverified:
            raise DownloadValidationError(f"No checksum is available for '{request.display_name}'.")

        with self.get_path_lock(request.destination):
            self._checkpoint(request, self._safe_size(request.temporary_path))
            valid = self.verify(request.destination, request.expected_size, request.hashes)
            if valid:
                self._checkpoint(request, self._safe_size(request.destination))
                size = request.destination.stat().st_size
                self._report(reporter, progress_stage, progress_message, size, size)
                download_journal.complete(request, size)
                return DownloadResult(request.destination, size, self.calculate_hashes(request.destination, request.hashes), 0, "cache")

            request.destination.parent.mkdir(parents=True, exist_ok=True)
            if request.force:
                self.delete_file(request.temporary_path)
            if self.verify(request.temporary_path, request.expected_size, request.hashes):
                self._checkpoint(request, self._safe_size(request.temporary_path))
                request.temporary_path.replace(request.destination)
                size = request.destination.stat().st_size
                self._report(reporter, progress_stage, progress_message, size, size)
                download_journal.complete(request, size)
                return DownloadResult(request.destination, size, self.calculate_hashes(request.destination, request.hashes), size, "partial-cache")

            last_error: Exception | None = None
            last_url = ""
            attempts_used = 0
            for url in request.urls:
                last_url = url
                host = (urlsplit(url).hostname or "unknown").casefold()
                for attempt in range(1, request.max_attempts + 1):
                    attempts_used += 1
                    self._checkpoint(request, self._safe_size(request.temporary_path))
                    response: httpx.Response | None = None
                    try:
                        with self._slot(host):
                            resumed_from, response = self._stream(request, url, reporter, progress_stage, progress_message, client_provider)
                        self._checkpoint(request, self._safe_size(request.temporary_path))
                        actual_hashes = self.calculate_hashes(request.temporary_path, request.hashes)
                        self._checkpoint(request, self._safe_size(request.temporary_path))
                        self._validate_file(request, actual_hashes)
                        self._checkpoint(request, self._safe_size(request.temporary_path))
                        request.temporary_path.replace(request.destination)
                        size = request.destination.stat().st_size
                        download_journal.complete(request, size)
                        self._report(reporter, progress_stage, progress_message, size, size)
                        return DownloadResult(request.destination, size, actual_hashes, resumed_from, url)
                    except DownloadCancelledError as error:
                        downloaded = self._safe_size(request.temporary_path)
                        self.delete_file(request.temporary_path)
                        download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(error))
                        raise
                    except DownloadPausedError as error:
                        download_journal.update(request, DownloadState.PAUSED, downloaded_bytes=self._safe_size(request.temporary_path), error=str(error))
                        raise
                    except Exception as error:
                        last_error = error
                        decision = DownloadRetryPolicy.decide(error, attempt, request.max_attempts)
                        if not decision.preserve_partial:
                            self.delete_file(request.temporary_path)
                        download_journal.update(request, DownloadState.FAILED, downloaded_bytes=self._safe_size(request.temporary_path), error=str(error))
                        if not decision.retry:
                            break
                        try:
                            download_pause_controller.wait(decision.delay_seconds)
                        except DownloadCancelledError as cancelled:
                            downloaded = self._safe_size(request.temporary_path)
                            self.delete_file(request.temporary_path)
                            download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(cancelled))
                            raise

            reason = self.describe_error(last_error)
            download_journal.update(request, DownloadState.FAILED, downloaded_bytes=self._safe_size(request.temporary_path), error=reason)
            raise DownloadFailedError(request.display_name, max(1, attempts_used), reason, url=last_url) from last_error

    def download_and_hash(self, url: str, path: Path, max_attempts: int = 2, timeout: float = 20.0, force: bool = False, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider=None) -> tuple[Path, str, int]:
        request = DownloadRequest(urls=(url,), destination=path, expected_size=0, hashes={"sha1": "0" * 40}, source="direct", display_name=path.name, max_attempts=max_attempts, timeout=timeout, force=force)
        with self.get_path_lock(path):
            self._checkpoint(request, self._safe_size(request.temporary_path))
            if path.is_file() and not force:
                sha1 = self.calculate_hash(path, "sha1")
                return path, sha1, path.stat().st_size
            if force:
                self.delete_file(request.temporary_path)
            last_error: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    with self._slot((urlsplit(url).hostname or "unknown").casefold()):
                        self._stream(request, url, reporter, progress_stage, progress_message, client_provider, skip_expected_hash=True)
                    self._checkpoint(request, self._safe_size(request.temporary_path))
                    sha1 = self.calculate_hash(request.temporary_path, "sha1")
                    size = request.temporary_path.stat().st_size
                    self._checkpoint(request, size)
                    request.temporary_path.replace(path)
                    download_journal.complete(request, size)
                    return path, sha1, size
                except DownloadCancelledError as error:
                    downloaded = self._safe_size(request.temporary_path)
                    self.delete_file(request.temporary_path)
                    download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(error))
                    raise
                except DownloadPausedError:
                    download_journal.update(request, DownloadState.PAUSED, downloaded_bytes=self._safe_size(request.temporary_path))
                    raise
                except Exception as error:
                    last_error = error
                    decision = DownloadRetryPolicy.decide(error, attempt, max_attempts)
                    if not decision.preserve_partial:
                        self.delete_file(request.temporary_path)
                    if not decision.retry:
                        break
                    try:
                        download_pause_controller.wait(decision.delay_seconds)
                    except DownloadCancelledError as cancelled:
                        downloaded = self._safe_size(request.temporary_path)
                        self.delete_file(request.temporary_path)
                        download_journal.update(request, DownloadState.CANCELLED, downloaded_bytes=downloaded, error=str(cancelled))
                        raise
            raise DownloadFailedError(path.name, max_attempts, self.describe_error(last_error), url=url) from last_error

    def _stream(self, request: DownloadRequest, url: str, reporter: ProgressReporter | None, stage: ProgressStage | None, message: str | None, client_provider=None, skip_expected_hash: bool = False, target_path: Path | None = None) -> tuple[int, httpx.Response]:
        force_full = False
        client_factory = client_provider or network_session.get_client
        temporary_path = Path(target_path) if target_path is not None else request.temporary_path
        while True:
            self._checkpoint(request, self._safe_size(temporary_path))
            if force_full:
                self.delete_file(temporary_path)
            existing = self.partial_size(temporary_path, request.expected_size)
            headers = {"Accept": "application/octet-stream", "Accept-Encoding": "identity", **dict(request.headers)}
            if existing > 0:
                headers["Range"] = f"bytes={existing}-"
            client = client_factory()
            if existing > 0:
                download_journal.start(request, existing)
            journal_progress = (existing, monotonic())
            with client.stream("GET", url, headers=headers, timeout=request.timeout) as response:
                status = int(getattr(response, "status_code", 200) or 200)
                if status == 416 and existing > 0 and not force_full:
                    force_full = True
                    continue
                response.raise_for_status()
                append = existing > 0 and status == 206
                if status == 206 and not self.valid_content_range(response, existing if append else 0, request.expected_size):
                    if existing > 0 and not force_full:
                        force_full = True
                        continue
                    raise DownloadValidationError(f"Invalid HTTP range response for '{request.display_name}'.")
                if not append:
                    existing = 0
                content_length = self.content_length(response, 0)
                range_total = self.content_range_total(response)
                total = request.expected_size or range_total or (existing + content_length if append else content_length)
                downloaded = existing
                response_bytes = 0
                last_percentage = -1
                rate_meter = DownloadRateMeter(downloaded)
                self._report(reporter, stage, message, downloaded, total)
                temporary_path.parent.mkdir(parents=True, exist_ok=True)
                with temporary_path.open("ab" if append else "wb") as output:
                    for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                        self._checkpoint(request, downloaded)
                        if not chunk:
                            continue
                        download_bandwidth_limiter.throttle(len(chunk))
                        self._checkpoint(request, downloaded)
                        output.write(chunk)
                        downloaded += len(chunk)
                        response_bytes += len(chunk)
                        if request.expected_size > 0 and downloaded > request.expected_size:
                            raise DownloadSizeMismatchError(f"Downloaded file '{request.display_name}' is larger than expected.")
                        if request.max_bytes > 0 and downloaded > request.max_bytes:
                            raise DownloadSizeMismatchError(f"Downloaded file '{request.display_name}' exceeds the allowed size limit.")
                        journal_progress = self._update_journal_progress(request, downloaded, journal_progress)
                        if total > 0:
                            percentage = min(int(downloaded * 100 / total), 100)
                            if percentage != last_percentage:
                                last_percentage = percentage
                                self._report(reporter, stage, message, downloaded, total, rate_meter.update(downloaded))
                    output.flush()
                if content_length > 0 and response_bytes != content_length:
                    raise DownloadSizeMismatchError(f"Incomplete HTTP response for '{request.display_name}': received {response_bytes} of {content_length} bytes.")
                if request.expected_size > 0 and downloaded != request.expected_size:
                    raise DownloadSizeMismatchError(f"Size mismatch for '{request.display_name}': received {downloaded} of {request.expected_size} bytes.")
                if total > 0 and last_percentage < 100:
                    self._report(reporter, stage, message, downloaded, total, rate_meter.update(downloaded))
                return existing, response

    def verify(self, path: Path, expected_size: int, hashes: dict | object) -> bool:
        if not Path(path).is_file():
            return False
        try:
            if expected_size > 0 and Path(path).stat().st_size != expected_size:
                return False
            expected = dict(hashes or {})
            if not expected:
                return True
            actual = self.calculate_hashes(Path(path), expected)
            return all(actual.get(algorithm) == value.lower() for algorithm, value in expected.items())
        except OSError:
            return False

    def _validate_file(self, request: DownloadRequest, actual_hashes: dict[str, str]) -> None:
        size = self._safe_size(request.temporary_path)
        if request.expected_size > 0 and size != request.expected_size:
            raise DownloadSizeMismatchError(f"Size mismatch for '{request.display_name}': received {size} of {request.expected_size} bytes.")
        for algorithm, expected in request.hashes.items():
            if actual_hashes.get(algorithm) != expected.lower():
                raise DownloadChecksumMismatchError(request.display_name, algorithm)

    @staticmethod
    def calculate_hash(path: Path, algorithm: str) -> str:
        normalized = str(algorithm).strip().lower()
        if normalized == "sha1":
            digest = hashlib.sha1(usedforsecurity=False)
        else:
            digest = hashlib.new(normalized)
        with Path(path).open("rb") as file:
            while chunk := file.read(1024 * 1024):
                download_pause_controller.raise_if_requested()
                digest.update(chunk)
        return digest.hexdigest().lower()

    def calculate_hashes(self, path: Path, expected: dict | object) -> dict[str, str]:
        return {algorithm: self.calculate_hash(path, algorithm) for algorithm in dict(expected or {})}

    @contextmanager
    def _slot(self, host: str):
        global_semaphore = self._global_semaphore
        host_semaphore = self._host_semaphores[host or "unknown"]
        global_acquired = False
        host_acquired = False
        try:
            while not global_acquired:
                download_pause_controller.raise_if_requested()
                global_acquired = global_semaphore.acquire(timeout=0.25)
            while not host_acquired:
                download_pause_controller.raise_if_requested()
                host_acquired = host_semaphore.acquire(timeout=0.25)
            yield
        finally:
            if host_acquired:
                host_semaphore.release()
            if global_acquired:
                global_semaphore.release()

    @staticmethod
    def _checkpoint(request: DownloadRequest, downloaded: int) -> None:
        was_paused = download_pause_controller.is_paused
        if was_paused:
            download_journal.update(request, DownloadState.PAUSED, downloaded_bytes=downloaded)
        download_pause_controller.raise_if_requested()
        if was_paused:
            download_journal.update(request, DownloadState.DOWNLOADING, downloaded_bytes=downloaded)

    @staticmethod
    def _update_journal_progress(request: DownloadRequest, downloaded: int, previous: tuple[int, float]) -> tuple[int, float]:
        now = monotonic()
        last_bytes, last_time = previous
        if downloaded - last_bytes < 4 * 1024 * 1024 and now - last_time < 1.0:
            return previous
        download_journal.update(request, DownloadState.DOWNLOADING, downloaded_bytes=downloaded)
        return downloaded, now

    @staticmethod
    def _report(reporter: ProgressReporter | None, stage: ProgressStage | None, message: str | None, current: int, total: int, bytes_per_second: float | None = None) -> None:
        if reporter is not None and stage is not None:
            reporter.bytes(stage=stage, message=message or "Downloading file...", current=max(0, current), total=max(0, total), bytes_per_second=bytes_per_second)

    @staticmethod
    def content_length(response: httpx.Response, fallback: int) -> int:
        try:
            return max(0, int(response.headers.get("Content-Length", fallback) or fallback))
        except ValueError:
            return fallback

    @staticmethod
    def parse_content_range(response: httpx.Response) -> tuple[int, int, int | None] | None:
        match = CONTENT_RANGE_PATTERN.fullmatch(str(response.headers.get("Content-Range", "")).strip())
        if match is None:
            return None
        start, end = int(match.group(1)), int(match.group(2))
        total = None if match.group(3) == "*" else int(match.group(3))
        return None if end < start else (start, end, total)

    @classmethod
    def valid_content_range(cls, response: httpx.Response, expected_start: int, expected_size: int) -> bool:
        parsed = cls.parse_content_range(response)
        if parsed is None:
            return False
        start, end, total = parsed
        if start != expected_start:
            return False
        content_length = cls.content_length(response, 0)
        if content_length > 0 and end - start + 1 != content_length:
            return False
        return not (expected_size > 0 and total is not None and total != expected_size)

    @classmethod
    def content_range_total(cls, response: httpx.Response) -> int:
        parsed = cls.parse_content_range(response)
        return 0 if parsed is None or parsed[2] is None else parsed[2]

    @classmethod
    def partial_size(cls, path: Path, expected_size: int) -> int:
        if not Path(path).is_file():
            return 0
        size = cls._safe_size(path)
        if expected_size > 0 and size > expected_size:
            cls.delete_file(path)
            return 0
        return size

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return max(0, Path(path).stat().st_size)
        except OSError:
            return 0

    @staticmethod
    def delete_file(path: Path) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def describe_error(error: Exception | None) -> str:
        if error is None:
            return "unknown error"
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code} from {error.request.url.host}"
        message = " ".join(str(error).split())
        return message or error.__class__.__name__


download_manager = DownloadManager()
