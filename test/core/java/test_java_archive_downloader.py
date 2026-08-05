from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest

from src.core.java.java_archive_downloader import JavaArchiveDownloader
from src.core.network.httpx_downloader import HttpDownloader
from src.models.java.java_release import JavaRelease


def test_java_download_uses_shared_bandwidth_limiter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = b"java-archive"
    release = JavaRelease(major=21, url="https://example.com/java.zip", sha256=hashlib.sha256(content).hexdigest(), size=len(content), filename="java.zip", release_name="test")
    throttled: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    monkeypatch.setattr(HttpDownloader, "_client", httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    monkeypatch.setattr("src.core.java.java_archive_downloader.download_bandwidth_limiter.throttle", lambda size: throttled.append(size))

    destination = tmp_path / "java.zip"
    JavaArchiveDownloader.download(release, destination, max_retry=1)

    assert destination.read_bytes() == content
    assert sum(throttled) == len(content)


def test_java_download_cancel_removes_partial_and_restarts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.network.download_pause import DownloadCancelledError, download_pause_controller

    content = b"java-archive"
    release = JavaRelease(major=21, url="https://example.com/java.zip", sha256=hashlib.sha256(content).hexdigest(), size=len(content), filename="java.zip", release_name="test")
    destination = tmp_path / "java.zip"
    phase = {"value": 1}
    ranges: list[str | None] = []

    class Response:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"Content-Length": str(len(content))}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int):
            if phase["value"] == 1:
                yield b"java-"
                download_pause_controller.request_cancel()
                yield b"archive"
                return
            yield content

    class Client:
        def stream(self, method: str, url: str, *, headers: dict[str, str], timeout: float):
            ranges.append(headers.get("Range"))
            return Response()

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: Client())
    download_pause_controller.begin()
    with pytest.raises(DownloadCancelledError):
        JavaArchiveDownloader.download(release, destination, max_retry=1)

    partial = destination.with_name(destination.name + ".part")
    assert partial.exists() is False

    download_pause_controller.finish()
    phase["value"] = 2
    download_pause_controller.begin()
    JavaArchiveDownloader.download(release, destination, max_retry=1)
    download_pause_controller.finish()

    assert destination.read_bytes() == content
    assert ranges == [None, None]
