from __future__ import annotations

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import errno
import time

import httpx

from src.core.network.download_pause import DownloadCancelledError
from src.core.network.network_errors import DownloadChecksumMismatchError, DownloadSizeMismatchError


@dataclass(frozen=True)
class RetryDecision:
    retry: bool
    preserve_partial: bool
    delay_seconds: float = 0.0
    reason: str = ""


class DownloadRetryPolicy:
    RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
    PERMANENT_STATUS_CODES = {400, 401, 403, 404, 405, 410, 422}
    PERMANENT_ERRNOS = {errno.EACCES, errno.EPERM, errno.ENOSPC, errno.EROFS, errno.ENAMETOOLONG}

    @classmethod
    def decide(cls, error: Exception, attempt: int, max_attempts: int) -> RetryDecision:
        if attempt >= max_attempts:
            return RetryDecision(False, cls._preserve_partial(error), reason="attempt limit reached")

        if isinstance(error, DownloadCancelledError):
            return RetryDecision(False, True, reason="cancelled")

        response = cls.response_for(error)
        if response is not None:
            status = int(response.status_code)
            if status in cls.RETRYABLE_STATUS_CODES:
                return RetryDecision(True, True, cls.retry_delay(attempt, response), f"HTTP {status}")
            return RetryDecision(False, False, reason=f"HTTP {status}")

        if isinstance(error, DownloadChecksumMismatchError):
            return RetryDecision(True, False, cls.retry_delay(attempt), "checksum mismatch")
        if isinstance(error, DownloadSizeMismatchError):
            return RetryDecision(True, False, cls.retry_delay(attempt), "size mismatch")
        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)):
            return RetryDecision(True, True, cls.retry_delay(attempt), error.__class__.__name__)
        if isinstance(error, OSError):
            if getattr(error, "errno", None) in cls.PERMANENT_ERRNOS:
                return RetryDecision(False, False, reason=error.__class__.__name__)
            return RetryDecision(True, True, cls.retry_delay(attempt), error.__class__.__name__)
        if isinstance(error, RuntimeError):
            lowered = str(error).casefold()
            permanent_markers = (
                "manual_download_required",
                "manual download required",
                "credentials are unavailable",
                "permission denied",
                "unsafe path",
                "invalid url",
            )
            if any(marker in lowered for marker in permanent_markers):
                return RetryDecision(False, False, reason="permanent runtime error")
            return RetryDecision(True, cls._preserve_partial(error), cls.retry_delay(attempt), "runtime error")
        if isinstance(error, httpx.HTTPError):
            return RetryDecision(True, True, cls.retry_delay(attempt), error.__class__.__name__)
        return RetryDecision(False, False, reason=error.__class__.__name__)

    @staticmethod
    def response_for(error: Exception | None) -> httpx.Response | None:
        return error.response if isinstance(error, httpx.HTTPStatusError) else None

    @staticmethod
    def retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = str(response.headers.get("Retry-After", "")).strip()
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), 30.0)
                except ValueError:
                    try:
                        retry_at = parsedate_to_datetime(retry_after)
                        return min(max(retry_at.timestamp() - time.time(), 0.0), 30.0)
                    except (TypeError, ValueError, OverflowError):
                        pass
        return float(min(2 ** max(0, attempt - 1), 8))

    @staticmethod
    def _preserve_partial(error: Exception) -> bool:
        return not isinstance(error, (DownloadChecksumMismatchError, DownloadSizeMismatchError))
