from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
import errno
import os
import socket
import ssl

import httpx

from src.core.network.download_manager import DownloadManager, download_manager
from src.core.network.download_models import DownloadRequest, DownloadResult
from src.core.network.download_pause import DownloadCancelledError, download_pause_controller
from src.core.network.network_errors import DownloadChecksumMismatchError, DownloadFailedError, DownloadSizeMismatchError, DownloadValidationError
from src.core.progress.progress_reporter import ProgressReporter
from src.models.network.artifact import ArtifactDownloadFailure, ArtifactRequest, DownloadFailureReason
from src.models.progress.progress_stage import ProgressStage


class ArtifactDownloadError(RuntimeError):
    def __init__(self, failure: ArtifactDownloadFailure) -> None:
        self.failure = failure
        super().__init__(f"{failure.reason.value}: {failure.detail}")


class ArtifactManualValidationError(RuntimeError):
    pass


class ArtifactDownloadService:
    _RETRYABLE_REASONS = {
        DownloadFailureReason.CONNECT_TIMEOUT,
        DownloadFailureReason.READ_TIMEOUT,
        DownloadFailureReason.DNS_ERROR,
        DownloadFailureReason.HTTP_429,
        DownloadFailureReason.HTTP_5XX,
        DownloadFailureReason.CONNECTION_RESET,
        DownloadFailureReason.SIZE_MISMATCH,
        DownloadFailureReason.HASH_MISMATCH,
        DownloadFailureReason.UNKNOWN,
    }

    def __init__(self, manager: DownloadManager | None = None) -> None:
        self._manager = manager or download_manager

    def download(self, request: ArtifactRequest, reporter: ProgressReporter | None = None, progress_stage: ProgressStage | None = None, progress_message: str | None = None, client_provider=None) -> DownloadResult:
        if not request.urls:
            raise ArtifactDownloadError(self.failure(request, DownloadValidationError("No download URL is available."), attempts=1))
        download_request = DownloadRequest(
            urls=request.urls,
            destination=request.destination,
            expected_size=request.expected_size,
            hashes=request.hashes,
            source=f"artifact:{request.provider}:{request.purpose}",
            display_name=request.expected_filename,
            max_attempts=request.max_attempts,
            timeout=request.timeout,
            headers=request.headers,
            force=request.force,
            allow_unverified=request.allow_unverified,
            max_bytes=request.max_bytes,
            operation_id=request.operation_id,
        )
        try:
            return self._manager.download(download_request, reporter=reporter, progress_stage=progress_stage, progress_message=progress_message, client_provider=client_provider)
        except DownloadCancelledError:
            self._manager.delete_file(download_request.temporary_path)
            raise
        except ArtifactDownloadError:
            raise
        except Exception as error:
            attempts = getattr(error, "attempts", request.max_attempts)
            raise ArtifactDownloadError(self.failure(request, error, attempts=attempts)) from error

    def verify_manual_file(self, request: ArtifactRequest, source: Path, allow_while_paused: bool = False) -> dict[str, str]:
        path = Path(source)
        self._manual_checkpoint(allow_while_paused)
        if not path.is_file():
            raise ArtifactManualValidationError("The selected file does not exist or cannot be read.")
        try:
            actual_size = path.stat().st_size
        except OSError as error:
            raise ArtifactManualValidationError(f"The selected file cannot be read: {error}") from error
        if request.expected_size > 0 and actual_size != request.expected_size:
            raise ArtifactManualValidationError(self.manual_mismatch_message(request))
        if request.hashes:
            try:
                actual_hashes = self._manager.calculate_hashes(path, request.hashes, allow_while_paused=allow_while_paused)
            except DownloadCancelledError:
                raise
            except (OSError, ValueError) as error:
                raise ArtifactManualValidationError(f"The selected file could not be verified: {error}") from error
            for algorithm, expected in request.hashes.items():
                if actual_hashes.get(algorithm) != expected.lower():
                    raise ArtifactManualValidationError(self.manual_mismatch_message(request))
            self._manual_checkpoint(allow_while_paused)
            return actual_hashes
        if not request.allow_unverified:
            if path.name.casefold() != request.expected_filename.casefold():
                raise ArtifactManualValidationError(self.manual_mismatch_message(request))
            if request.expected_size <= 0:
                raise ArtifactManualValidationError(f"The required artifact '{request.expected_filename}' has no checksum or size metadata and cannot be verified safely.")
        self._manual_checkpoint(allow_while_paused)
        return {}

    def accept_manual_file(self, request: ArtifactRequest, source: Path, allow_while_paused: bool = False) -> Path:
        source_path = Path(source)
        self.verify_manual_file(request, source_path, allow_while_paused=allow_while_paused)
        destination = Path(request.destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if source_path.resolve() == destination.resolve():
                return destination
        except OSError:
            pass

        temporary = destination.with_name(destination.name + ".part")
        self._manager.delete_file(temporary)
        try:
            self._manual_checkpoint(allow_while_paused)
            with source_path.open("rb") as input_file, temporary.open("wb") as output_file:
                while chunk := input_file.read(1024 * 1024):
                    self._manual_checkpoint(allow_while_paused)
                    output_file.write(chunk)
                output_file.flush()
                try:
                    os.fsync(output_file.fileno())
                except OSError:
                    pass
            self._manual_checkpoint(allow_while_paused)
            self.verify_manual_file(
                ArtifactRequest(
                    provider=request.provider,
                    purpose=request.purpose,
                    destination=temporary,
                    expected_filename=request.expected_filename,
                    expected_size=request.expected_size,
                    hashes=request.hashes,
                    project_id=request.project_id,
                    version_id=request.version_id,
                    file_id=request.file_id,
                    allow_unverified=request.allow_unverified,
                ),
                temporary,
                allow_while_paused=allow_while_paused,
            )
            self._manual_checkpoint(allow_while_paused)
            temporary.replace(destination)
            return destination
        except DownloadCancelledError:
            self._manager.delete_file(temporary)
            raise
        except Exception:
            self._manager.delete_file(temporary)
            raise

    @staticmethod
    def _manual_checkpoint(allow_while_paused: bool) -> None:
        if allow_while_paused:
            download_pause_controller.raise_if_cancel_requested()
            return
        download_pause_controller.raise_if_requested()

    def failure(self, request: ArtifactRequest, error: BaseException | None, attempts: int = 1) -> ArtifactDownloadFailure:
        root = self._root_error(error)
        reason, status = self._classify(root)
        detail = self._detail(root)
        url = self._error_url(root) or request.direct_url
        retryable = reason in self._RETRYABLE_REASONS
        if reason in {DownloadFailureReason.NO_DOWNLOAD_URL, DownloadFailureReason.HTTP_403, DownloadFailureReason.HTTP_404, DownloadFailureReason.FILE_ACCESS_ERROR, DownloadFailureReason.DISK_SPACE_ERROR, DownloadFailureReason.CANCELLED}:
            retryable = False
        return ArtifactDownloadFailure(
            provider=request.provider,
            filename=request.expected_filename,
            reason=reason,
            detail=detail,
            url=url,
            page_url=request.page_url,
            project_url=request.project_url,
            http_status=status,
            attempts=max(1, int(attempts or 1)),
            retryable=retryable,
            project_id=request.project_id,
            version_id=request.version_id,
            file_id=request.file_id,
        )

    @staticmethod
    def manual_mismatch_message(request: ArtifactRequest) -> str:
        return f"The selected file does not match the artifact required by the modpack. Expected: {request.expected_filename}"

    @staticmethod
    def safe_destination(root: Path, relative_path: str) -> tuple[Path, str]:
        normalized = str(relative_path).replace("\\", "/").strip()
        relative = PurePosixPath(normalized)
        if not normalized or relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise RuntimeError(f"Unsafe artifact destination path: {relative_path!r}")
        if ":" in relative.parts[0]:
            raise RuntimeError(f"Unsafe Windows artifact destination path: {relative_path!r}")
        root_path = Path(root).resolve(strict=False)
        destination = root_path.joinpath(*relative.parts).resolve(strict=False)
        try:
            destination.relative_to(root_path)
        except ValueError as error:
            raise RuntimeError(f"Artifact destination escapes its instance root: {relative_path!r}") from error
        return destination, relative.as_posix()

    @staticmethod
    def _root_error(error: BaseException | None) -> BaseException | None:
        current = error
        visited: set[int] = set()
        candidate = current
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            if isinstance(current, DownloadFailedError) and current.__cause__ is not None:
                current = current.__cause__
                candidate = current
                continue
            candidate = current
            current = current.__cause__ or current.__context__
        return candidate

    @staticmethod
    def _classify(error: BaseException | None) -> tuple[DownloadFailureReason, int | None]:
        if error is None:
            return DownloadFailureReason.UNKNOWN, None
        if isinstance(error, DownloadCancelledError):
            return DownloadFailureReason.CANCELLED, None
        if isinstance(error, DownloadChecksumMismatchError):
            return DownloadFailureReason.HASH_MISMATCH, None
        if isinstance(error, DownloadSizeMismatchError):
            return DownloadFailureReason.SIZE_MISMATCH, None
        if isinstance(error, DownloadValidationError) and "no download url" in str(error).casefold():
            return DownloadFailureReason.NO_DOWNLOAD_URL, None
        if isinstance(error, httpx.HTTPStatusError):
            status = int(error.response.status_code)
            if status == 403:
                return DownloadFailureReason.HTTP_403, status
            if status == 404:
                return DownloadFailureReason.HTTP_404, status
            if status == 429:
                return DownloadFailureReason.HTTP_429, status
            if 500 <= status <= 599:
                return DownloadFailureReason.HTTP_5XX, status
            return DownloadFailureReason.UNKNOWN, status
        if isinstance(error, httpx.ConnectTimeout):
            return DownloadFailureReason.CONNECT_TIMEOUT, None
        if isinstance(error, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
            return DownloadFailureReason.READ_TIMEOUT, None
        if isinstance(error, httpx.TooManyRedirects):
            return DownloadFailureReason.TOO_MANY_REDIRECTS, None
        if isinstance(error, (ssl.SSLError, httpx.ProxyError)):
            return DownloadFailureReason.TLS_ERROR, None
        if isinstance(error, socket.gaierror):
            return DownloadFailureReason.DNS_ERROR, None
        if isinstance(error, (ConnectionResetError, BrokenPipeError)):
            return DownloadFailureReason.CONNECTION_RESET, None
        if isinstance(error, httpx.ConnectError):
            nested = ArtifactDownloadService._find_nested(error, (socket.gaierror, ssl.SSLError, ConnectionResetError))
            if isinstance(nested, socket.gaierror):
                return DownloadFailureReason.DNS_ERROR, None
            if isinstance(nested, ssl.SSLError):
                return DownloadFailureReason.TLS_ERROR, None
            if isinstance(nested, ConnectionResetError) or "reset" in str(error).casefold():
                return DownloadFailureReason.CONNECTION_RESET, None
            return DownloadFailureReason.CONNECTION_RESET, None
        if isinstance(error, (httpx.NetworkError, httpx.RemoteProtocolError)):
            return DownloadFailureReason.CONNECTION_RESET, None
        if isinstance(error, OSError):
            if getattr(error, "errno", None) == errno.ENOSPC:
                return DownloadFailureReason.DISK_SPACE_ERROR, None
            if getattr(error, "errno", None) in {errno.EACCES, errno.EPERM, errno.EROFS, errno.ENAMETOOLONG}:
                return DownloadFailureReason.FILE_ACCESS_ERROR, None
        message = str(error).casefold()
        if "no download url" in message or "no download source" in message:
            return DownloadFailureReason.NO_DOWNLOAD_URL, None
        if "checksum" in message or "sha-1 mismatch" in message or "sha-512 mismatch" in message or "hash mismatch" in message:
            return DownloadFailureReason.HASH_MISMATCH, None
        if "size mismatch" in message or "incomplete http response" in message:
            return DownloadFailureReason.SIZE_MISMATCH, None
        if "disk" in message and ("full" in message or "space" in message):
            return DownloadFailureReason.DISK_SPACE_ERROR, None
        if "permission" in message or "access denied" in message or "read-only" in message:
            return DownloadFailureReason.FILE_ACCESS_ERROR, None
        return DownloadFailureReason.UNKNOWN, None

    @staticmethod
    def _find_nested(error: BaseException, types: tuple[type[BaseException], ...]) -> BaseException | None:
        current: BaseException | None = error
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            if isinstance(current, types):
                return current
            visited.add(id(current))
            current = current.__cause__ or current.__context__
        return None

    @staticmethod
    def _detail(error: BaseException | None) -> str:
        if error is None:
            return "Unknown download error."
        if isinstance(error, httpx.HTTPStatusError):
            host = error.request.url.host or "remote server"
            return f"HTTP {error.response.status_code} from {host}."
        message = " ".join(str(error).split())
        return message or error.__class__.__name__

    @staticmethod
    def _error_url(error: BaseException | None) -> str:
        try:
            request = getattr(error, "request", None)
        except RuntimeError:
            request = None
        url = getattr(request, "url", None)
        if url is not None:
            return str(url)
        if isinstance(error, DownloadFailedError):
            return str(getattr(error, "url", "") or "")
        return ""


def is_local_artifact_storage_error(error: BaseException | None) -> bool:
    """Return whether an artifact failure can only be fixed by freeing/fixing local storage."""
    return isinstance(error, ArtifactDownloadError) and error.failure.reason in {
        DownloadFailureReason.DISK_SPACE_ERROR,
        DownloadFailureReason.FILE_ACCESS_ERROR,
    }


artifact_download_service = ArtifactDownloadService()
