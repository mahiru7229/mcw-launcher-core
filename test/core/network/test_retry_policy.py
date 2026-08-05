from __future__ import annotations

import httpx

from src.core.network.download_pause import DownloadCancelledError
from src.core.network.network_errors import DownloadChecksumMismatchError
from src.core.network.retry_policy import DownloadRetryPolicy


def _status_error(status: int, headers: dict[str, str] | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.com/file.jar")
    response = httpx.Response(status, headers=headers or {}, request=request)
    return httpx.HTTPStatusError(f"HTTP {status}", request=request, response=response)


def test_permanent_http_error_is_not_retried() -> None:
    decision = DownloadRetryPolicy.decide(_status_error(403), attempt=1, max_attempts=3)

    assert decision.retry is False
    assert decision.preserve_partial is False
    assert decision.reason == "HTTP 403"


def test_retryable_http_error_uses_retry_after() -> None:
    decision = DownloadRetryPolicy.decide(_status_error(429, {"Retry-After": "2"}), attempt=1, max_attempts=3)

    assert decision.retry is True
    assert decision.preserve_partial is True
    assert decision.delay_seconds == 2.0


def test_checksum_mismatch_retries_without_preserving_partial() -> None:
    decision = DownloadRetryPolicy.decide(DownloadChecksumMismatchError("example.jar", "sha1"), attempt=1, max_attempts=3)

    assert decision.retry is True
    assert decision.preserve_partial is False


def test_cancel_is_terminal_but_preserves_partial() -> None:
    decision = DownloadRetryPolicy.decide(DownloadCancelledError("cancelled"), attempt=1, max_attempts=3)

    assert decision.retry is False
    assert decision.preserve_partial is True
