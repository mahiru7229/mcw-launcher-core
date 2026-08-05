from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

import src.core.network.download_manager as download_manager_module
from src.core.network.download_journal import DownloadJournal
from src.core.network.download_manager import DownloadManager
from src.core.network.download_models import DownloadRequest, DownloadState
from src.core.network.network_errors import DownloadFailedError


class Response:
    def __init__(self, status: int, content: bytes, headers: dict[str, str] | None = None, url: str = "https://example.com/file.jar") -> None:
        self.status_code = status
        self._content = content
        self.headers = dict(headers or {})
        self.request = httpx.Request("GET", url)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request)
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=self.request, response=response)

    def iter_bytes(self, chunk_size: int):
        yield self._content


class Client:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = list(responses)
        self.ranges: list[str | None] = []
        self.urls: list[str] = []

    def stream(self, method: str, url: str, *, headers: dict[str, str], timeout: object):
        self.urls.append(url)
        self.ranges.append(headers.get("Range"))
        response = self.responses.pop(0)
        response.request = httpx.Request("GET", url)
        return response


@pytest.fixture
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DownloadManager:
    journal = DownloadJournal(tmp_path / "journal.json")
    monkeypatch.setattr(download_manager_module, "download_journal", journal)
    return DownloadManager()


def _request(destination: Path, content: bytes, urls: tuple[str, ...] = ("https://example.com/file.jar",), attempts: int = 2) -> DownloadRequest:
    return DownloadRequest(
        urls=urls,
        destination=destination,
        expected_size=len(content),
        hashes={"sha1": hashlib.sha1(content).hexdigest()},
        source="test",
        display_name=destination.name,
        max_attempts=attempts,
        request_id="download-1",
    )


def test_download_uses_part_file_verifies_and_atomically_replaces(manager: DownloadManager, tmp_path: Path) -> None:
    content = b"complete-content"
    destination = tmp_path / "file.jar"
    client = Client([Response(200, content, {"Content-Length": str(len(content))})])

    result = manager.download(_request(destination, content), client_provider=lambda: client)

    assert result.path == destination
    assert destination.read_bytes() == content
    assert destination.with_name("file.jar.part").exists() is False
    assert client.ranges == [None]
    assert (tmp_path / "journal.json").exists() is False


def test_auto_concurrency_does_not_bottleneck_single_download_host(manager: DownloadManager) -> None:
    assert manager.configure() == (8, 8)
    assert manager.configure(12) == (12, 8)
    assert manager.configure(4) == (4, 4)


def test_download_resumes_valid_partial_with_range(manager: DownloadManager, tmp_path: Path) -> None:
    content = b"abcdef"
    destination = tmp_path / "file.jar"
    destination.with_name("file.jar.part").write_bytes(b"abc")
    client = Client([Response(206, b"def", {"Content-Length": "3", "Content-Range": "bytes 3-5/6"})])

    result = manager.download(_request(destination, content), client_provider=lambda: client)

    assert result.resumed_from == 3
    assert destination.read_bytes() == content
    assert client.ranges == ["bytes=3-"]


def test_permanent_error_moves_to_next_verified_source_without_retrying(manager: DownloadManager, tmp_path: Path) -> None:
    content = b"mirror-content"
    destination = tmp_path / "file.jar"
    urls = ("https://first.example.com/file.jar", "https://second.example.com/file.jar")
    client = Client([
        Response(403, b"", url=urls[0]),
        Response(200, content, {"Content-Length": str(len(content))}, url=urls[1]),
    ])

    result = manager.download(_request(destination, content, urls=urls, attempts=3), client_provider=lambda: client)

    assert result.source_url == urls[1]
    assert client.urls == list(urls)
    assert destination.read_bytes() == content


def test_all_permanent_sources_fail_without_repeated_attempts(manager: DownloadManager, tmp_path: Path) -> None:
    content = b"expected"
    destination = tmp_path / "file.jar"
    urls = ("https://first.example.com/file.jar", "https://second.example.com/file.jar")
    client = Client([Response(403, b"", url=urls[0]), Response(404, b"", url=urls[1])])

    with pytest.raises(DownloadFailedError):
        manager.download(_request(destination, content, urls=urls, attempts=3), client_provider=lambda: client)

    assert client.urls == list(urls)
    assert destination.exists() is False
    assert destination.with_name("file.jar.part").exists() is False
    entries = DownloadJournal(tmp_path / "journal.json").recoverable_entries()
    assert entries[0]["state"] == DownloadState.FAILED.value
