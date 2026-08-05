import hashlib
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.core.network.httpx_downloader import (
    CHUNK_SIZE,
    HttpDownloader,
)
from src.core.network.download_journal import DownloadJournal
from src.models.progress.progress_stage import ProgressStage


class DummyResponse:
    def __init__(
        self,
        *,
        chunks: list[bytes],
        headers: dict[str, str] | None = None,
        status_error: Exception | None = None,
        status_code: int = 200,
    ):
        self._chunks = chunks
        self.headers = headers or {}
        self._status_error = status_error
        self.status_code = status_code
        self.requested_chunk_size = None

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def iter_bytes(self, chunk_size: int):
        self.requested_chunk_size = chunk_size
        yield from self._chunks


class DummyClient:
    def __init__(
        self,
        response: DummyResponse,
    ):
        self.response = response
        self.received = {}

    def stream(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float,
    ):
        self.received = {
            "method": method,
            "url": url,
            "headers": headers or {},
            "timeout": timeout,
        }
        return self.response


class DummyReporter:
    def __init__(self):
        self.events = []

    def bytes(
        self,
        *,
        stage,
        message,
        current,
        total,
        bytes_per_second=None,
    ):
        self.events.append(
            {
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
            }
        )


def make_download_info(
    *,
    content: bytes = b"hello",
    url: str = "https://example.com/file.jar",
):
    return SimpleNamespace(
        url=url,
        sha1=hashlib.sha1(content).hexdigest(),
        size=len(content),
    )


@pytest.fixture(autouse=True)
def reset_http_downloader_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    journal = DownloadJournal(tmp_path / "download-journal.json")
    monkeypatch.setattr("src.core.network.httpx_downloader.download_journal", journal)
    monkeypatch.setattr("src.core.network.download_manager.download_journal", journal)
    HttpDownloader.close_client()
    HttpDownloader._path_locks.clear()

    yield

    HttpDownloader.close_client()
    HttpDownloader._path_locks.clear()


def test_get_client_creates_shared_httpx_client():
    client = HttpDownloader.get_client()

    assert isinstance(client, httpx.Client)
    assert HttpDownloader.get_client() is client


def test_get_client_recreates_closed_client():
    first = HttpDownloader.get_client()
    first.close()

    second = HttpDownloader.get_client()

    assert second is not first
    assert second.is_closed is False


def test_close_client_closes_and_clears_client():
    client = HttpDownloader.get_client()

    HttpDownloader.close_client()

    assert client.is_closed is True
    assert HttpDownloader._client is None


def test_close_client_is_safe_when_no_client_exists():
    HttpDownloader._client = None

    HttpDownloader.close_client()

    assert HttpDownloader._client is None


def test_get_path_lock_returns_same_lock_for_same_path(
    tmp_path: Path,
):
    path = tmp_path / "file.jar"

    first = HttpDownloader._get_path_lock(path)
    second = HttpDownloader._get_path_lock(path)

    assert first is second


def test_get_path_lock_normalizes_equivalent_paths(
    tmp_path: Path,
):
    direct = tmp_path / "folder" / "file.jar"
    equivalent = (
        tmp_path
        / "folder"
        / ".."
        / "folder"
        / "file.jar"
    )

    assert (
        HttpDownloader._get_path_lock(direct)
        is HttpDownloader._get_path_lock(equivalent)
    )


def test_download_passes_arguments_to_download_and_verify(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    info = make_download_info()
    path = tmp_path / "file.jar"
    reporter = object()
    received = {}

    def fake_download_and_verify(**kwargs):
        received.update(kwargs)
        return path

    monkeypatch.setattr(
        HttpDownloader,
        "_download_and_verify",
        fake_download_and_verify,
    )

    result = HttpDownloader.download(
        download_info=info,
        path=path,
        max_retry=4,
        timeout=12.5,
        reporter=reporter,
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
        progress_message="Downloading client",
    )

    assert result == path
    assert received == {
        "download_info": info,
        "path": path,
        "max_retry": 4,
        "timeout": 12.5,
        "reporter": reporter,
        "progress_stage": ProgressStage.DOWNLOADING_CLIENT,
        "progress_message": "Downloading client",
    }


def test_download_stream_writes_all_non_empty_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    chunks = [
        b"hello",
        b"",
        b" ",
        b"world",
    ]
    response = DummyResponse(
        chunks=chunks,
        headers={
            "Content-Length": "11"
        },
    )
    client = DummyClient(response)

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: client,
    )

    path = tmp_path / "nested" / "file.jar"
    info = make_download_info(
        content=b"hello world"
    )

    HttpDownloader._download_stream(
        download_info=info,
        path=path,
        timeout=15.0,
    )

    assert path.read_bytes() == b"hello world"
    assert client.received == {
        "method": "GET",
        "url": info.url,
        "headers": {"Accept": "application/octet-stream", "Accept-Encoding": "identity"},
        "timeout": 15.0,
    }
    assert response.requested_chunk_size == CHUNK_SIZE


def test_download_stream_creates_parent_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    response = DummyResponse(
        chunks=[b"data"],
    )
    client = DummyClient(response)

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: client,
    )

    path = tmp_path / "missing" / "nested" / "file.jar"

    HttpDownloader._download_stream(
        download_info=make_download_info(
            content=b"data"
        ),
        path=path,
        timeout=20.0,
    )

    assert path.parent.exists()


def test_download_stream_raises_http_status_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    request = httpx.Request(
        "GET",
        "https://example.com/file.jar",
    )
    response_obj = httpx.Response(
        404,
        request=request,
    )
    error = httpx.HTTPStatusError(
        "not found",
        request=request,
        response=response_obj,
    )
    response = DummyResponse(
        chunks=[],
        status_error=error,
    )

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: DummyClient(response),
    )

    with pytest.raises(httpx.HTTPStatusError):
        HttpDownloader._download_stream(
            download_info=make_download_info(),
            path=tmp_path / "file.jar",
            timeout=20.0,
        )


def test_download_stream_uses_content_length_for_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    response = DummyResponse(
        chunks=[
            b"12345",
            b"67890",
        ],
        headers={
            "Content-Length": "10"
        },
    )
    reporter = DummyReporter()

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: DummyClient(response),
    )

    HttpDownloader._download_stream(
        download_info=make_download_info(
            content=b"1234567890"
        ),
        path=tmp_path / "file.jar",
        timeout=20.0,
        reporter=reporter,
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
        progress_message="Downloading client",
    )

    assert reporter.events == [
        {
            "stage": ProgressStage.DOWNLOADING_CLIENT,
            "message": "Downloading client",
            "current": 0,
            "total": 10,
        },
        {
            "stage": ProgressStage.DOWNLOADING_CLIENT,
            "message": "Downloading client",
            "current": 5,
            "total": 10,
        },
        {
            "stage": ProgressStage.DOWNLOADING_CLIENT,
            "message": "Downloading client",
            "current": 10,
            "total": 10,
        },
    ]


def test_download_stream_falls_back_to_metadata_size_for_invalid_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    response = DummyResponse(
        chunks=[b"data"],
        headers={
            "Content-Length": "invalid"
        },
    )
    reporter = DummyReporter()
    info = make_download_info(
        content=b"data"
    )

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: DummyClient(response),
    )

    HttpDownloader._download_stream(
        download_info=info,
        path=tmp_path / "file.jar",
        timeout=20.0,
        reporter=reporter,
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
    )

    assert all(
        event["total"] == info.size
        for event in reporter.events
    )


def test_download_stream_uses_metadata_size_without_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    response = DummyResponse(
        chunks=[b"data"],
        headers={},
    )
    reporter = DummyReporter()
    info = make_download_info(
        content=b"data"
    )

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: DummyClient(response),
    )

    HttpDownloader._download_stream(
        download_info=info,
        path=tmp_path / "file.jar",
        timeout=20.0,
        reporter=reporter,
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
    )

    assert reporter.events[0]["total"] == info.size


def test_download_stream_uses_default_progress_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    response = DummyResponse(
        chunks=[b"data"],
        headers={
            "Content-Length": "4"
        },
    )
    reporter = DummyReporter()

    monkeypatch.setattr(
        HttpDownloader,
        "get_client",
        lambda: DummyClient(response),
    )

    HttpDownloader._download_stream(
        download_info=make_download_info(
            content=b"data"
        ),
        path=tmp_path / "file.jar",
        timeout=20.0,
        reporter=reporter,
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
        progress_message=None,
    )

    assert all(
        event["message"] == "Downloading file..."
        for event in reporter.events
    )


def test_report_progress_does_nothing_without_reporter():
    HttpDownloader._report_progress(
        reporter=None,
        stage=ProgressStage.DOWNLOADING_CLIENT,
        message="Downloading",
        current=0,
        total=100,
    )


def test_report_progress_does_nothing_without_stage():
    reporter = DummyReporter()

    HttpDownloader._report_progress(
        reporter=reporter,
        stage=None,
        message="Downloading",
        current=0,
        total=100,
    )

    assert reporter.events == []


def test_verify_sha1_returns_true_for_matching_file(
    tmp_path: Path,
):
    content = b"MCW Launcher"
    path = tmp_path / "file.jar"
    path.write_bytes(content)

    expected = hashlib.sha1(content).hexdigest()

    assert HttpDownloader.verify_sha1(
        path,
        expected,
    ) is True


def test_verify_sha1_is_case_insensitive(
    tmp_path: Path,
):
    content = b"MCW Launcher"
    path = tmp_path / "file.jar"
    path.write_bytes(content)

    expected = hashlib.sha1(
        content
    ).hexdigest().upper()

    assert HttpDownloader.verify_sha1(
        path,
        expected,
    ) is True


def test_verify_sha1_returns_false_for_mismatch(
    tmp_path: Path,
):
    path = tmp_path / "file.jar"
    path.write_bytes(b"wrong")

    assert HttpDownloader.verify_sha1(
        path,
        "0" * 40,
    ) is False


def test_verify_sha1_returns_false_for_missing_file(
    tmp_path: Path,
):
    assert HttpDownloader.verify_sha1(
        tmp_path / "missing.jar",
        "0" * 40,
    ) is False


def test_verify_sha1_returns_false_for_directory(
    tmp_path: Path,
):
    assert HttpDownloader.verify_sha1(
        tmp_path,
        "0" * 40,
    ) is False


def test_delete_file_removes_existing_file(
    tmp_path: Path,
):
    path = tmp_path / "file.part"
    path.write_bytes(b"partial")

    HttpDownloader.delete_file(path)

    assert not path.exists()


def test_delete_file_is_safe_for_missing_file(
    tmp_path: Path,
):
    HttpDownloader.delete_file(
        tmp_path / "missing.part"
    )


def test_download_and_verify_rejects_invalid_retry_count(
    tmp_path: Path,
):
    with pytest.raises(
        ValueError,
        match="max_retry must be at least 1",
    ):
        HttpDownloader._download_and_verify(
            download_info=make_download_info(),
            path=tmp_path / "file.jar",
            max_retry=0,
            timeout=20.0,
        )


def test_download_and_verify_returns_valid_cached_file_without_download(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    path = tmp_path / "file.jar"
    path.write_bytes(b"cached")

    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda received_path, sha1: (
            received_path == path
        ),
    )

    def fail_download(*args, **kwargs):
        raise AssertionError(
            "cached file should not be downloaded"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        fail_download,
    )

    assert HttpDownloader._download_and_verify(
        download_info=make_download_info(
            content=b"cached"
        ),
        path=path,
        max_retry=2,
        timeout=20.0,
    ) == path


def test_download_and_verify_downloads_to_part_then_replaces_target(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    content = b"downloaded"
    info = make_download_info(
        content=content
    )
    path = tmp_path / "file.jar"
    temp_path = tmp_path / "file.jar.part"
    received = {}

    def fake_stream(**kwargs):
        received.update(kwargs)
        kwargs["path"].write_bytes(content)

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        fake_stream,
    )

    result = HttpDownloader._download_and_verify(
        download_info=info,
        path=path,
        max_retry=2,
        timeout=9.0,
        reporter="reporter",
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
        progress_message="Downloading client",
    )

    assert result == path
    assert path.read_bytes() == content
    assert not temp_path.exists()
    assert received == {
        "download_info": info,
        "path": temp_path,
        "timeout": 9.0,
        "reporter": "reporter",
        "progress_stage": ProgressStage.DOWNLOADING_CLIENT,
        "progress_message": "Downloading client",
    }


def test_download_and_verify_retries_after_http_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    content = b"success"
    info = make_download_info(
        content=content
    )
    path = tmp_path / "file.jar"
    attempts = []
    sleeps = []

    def fake_stream(**kwargs):
        attempts.append(kwargs["path"])

        if len(attempts) == 1:
            raise httpx.ConnectError(
                "connection failed"
            )

        kwargs["path"].write_bytes(content)

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "src.core.network.httpx_downloader.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    result = HttpDownloader._download_and_verify(
        download_info=info,
        path=path,
        max_retry=2,
        timeout=20.0,
    )

    assert result == path
    assert len(attempts) == 2
    assert sleeps == [1]


def test_download_and_verify_uses_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    info = make_download_info()
    path = tmp_path / "file.jar"
    sleeps = []

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        lambda **kwargs: (_ for _ in ()).throw(
            OSError("disk failure")
        ),
    )
    monkeypatch.setattr(
        "src.core.network.httpx_downloader.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    with pytest.raises(RuntimeError):
        HttpDownloader._download_and_verify(
            download_info=info,
            path=path,
            max_retry=5,
            timeout=20.0,
        )

    assert sleeps == [
        1,
        2,
        4,
        8,
    ]


def test_download_and_verify_retries_sha1_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    info = make_download_info(
        content=b"correct"
    )
    path = tmp_path / "file.jar"
    attempts = []
    sleeps = []

    def fake_stream(**kwargs):
        attempts.append(1)

        if len(attempts) == 1:
            kwargs["path"].write_bytes(
                b"wrong"
            )
        else:
            kwargs["path"].write_bytes(
                b"correct"
            )

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        fake_stream,
    )
    monkeypatch.setattr(
        "src.core.network.httpx_downloader.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    assert HttpDownloader._download_and_verify(
        download_info=info,
        path=path,
        max_retry=2,
        timeout=20.0,
    ) == path

    assert len(attempts) == 2
    assert sleeps == [1]


def test_download_and_verify_preserves_part_file_after_retryable_final_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    info = make_download_info()
    path = tmp_path / "file.jar"
    temp_path = tmp_path / "file.jar.part"

    def failing_stream(**kwargs):
        kwargs["path"].write_bytes(
            b"partial"
        )
        raise OSError(
            "download failed"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        failing_stream,
    )
    monkeypatch.setattr(
        "src.core.network.httpx_downloader.time.sleep",
        lambda seconds: None,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Failed to download 'file.jar' "
            "after 2 attempts"
        ),
    ):
        HttpDownloader._download_and_verify(
            download_info=info,
            path=path,
            max_retry=2,
            timeout=20.0,
        )

    assert temp_path.read_bytes() == b"partial"
    assert not path.exists()


def test_download_and_verify_chains_last_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    expected = OSError("last failure")

    monkeypatch.setattr(
        HttpDownloader,
        "_download_stream",
        lambda **kwargs: (_ for _ in ()).throw(
            expected
        ),
    )
    monkeypatch.setattr(
        "src.core.network.httpx_downloader.time.sleep",
        lambda seconds: None,
    )

    with pytest.raises(RuntimeError) as error:
        HttpDownloader._download_and_verify(
            download_info=make_download_info(),
            path=tmp_path / "file.jar",
            max_retry=1,
            timeout=20.0,
        )

    assert error.value.__cause__ is expected

def test_download_and_hash_writes_file_and_returns_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = b"fabric-library"
    response = DummyResponse(chunks=[content[:6], content[6:]], headers={"Content-Length": str(len(content))})
    client = DummyClient(response)
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: client)
    path = tmp_path / "libraries" / "fabric.jar"

    downloaded, sha1, size = HttpDownloader.download_and_hash("https://example.com/fabric.jar", path)

    assert downloaded == path
    assert path.read_bytes() == content
    assert sha1 == hashlib.sha1(content).hexdigest()
    assert size == len(content)


def test_download_and_hash_reuses_existing_file_without_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    path = tmp_path / "fabric.jar"
    path.write_bytes(b"cached")
    monkeypatch.setattr(HttpDownloader, "get_client", lambda: (_ for _ in ()).throw(AssertionError("network should not be used")))

    downloaded, sha1, size = HttpDownloader.download_and_hash("https://example.com/fabric.jar", path)

    assert downloaded == path
    assert sha1 == hashlib.sha1(b"cached").hexdigest()
    assert size == 6


def test_download_resumes_after_interrupted_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = (b"a" * CHUNK_SIZE) + b"end"
    path = tmp_path / "file.jar"
    requests: list[str | None] = []

    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield content[:CHUNK_SIZE]
            raise httpx.ReadError("connection dropped")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Range"))
        if len(requests) == 1:
            return httpx.Response(200, headers={"Content-Length": str(len(content))}, stream=BrokenStream())
        return httpx.Response(206, headers={"Content-Length": "3", "Content-Range": f"bytes {CHUNK_SIZE}-{len(content) - 1}/{len(content)}"}, content=content[CHUNK_SIZE:])

    HttpDownloader._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr("src.core.network.httpx_downloader.time.sleep", lambda seconds: None)

    result = HttpDownloader.download(make_download_info(content=content), path, max_retry=2)

    assert result.read_bytes() == content
    assert requests == [None, f"bytes={CHUNK_SIZE}-"]


def test_download_restarts_full_after_range_not_satisfiable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    content = b"abcdef"
    path = tmp_path / "file.jar"
    path.with_name(path.name + ".part").write_bytes(content[:3])
    requests: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Range"))
        if len(requests) == 1:
            return httpx.Response(416, headers={"Content-Range": "bytes */6"})
        return httpx.Response(200, headers={"Content-Length": "6"}, content=content)

    HttpDownloader._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)

    result = HttpDownloader.download(make_download_info(content=content), path, max_retry=1)

    assert result.read_bytes() == content
    assert requests == ["bytes=3-", None]


def test_download_fails_fast_for_non_retryable_http_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    path = tmp_path / "file.jar"
    requests = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(404)

    HttpDownloader._client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr("src.core.network.httpx_downloader.time.sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(RuntimeError, match="HTTP 404"):
        HttpDownloader.download(make_download_info(), path, max_retry=5)

    assert len(requests) == 1
    assert sleeps == []


def test_download_stream_reports_network_speed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from src.core.progress.download_rate_meter import DownloadRateMeter
    from src.core.progress.progress_reporter import ProgressReporter

    response = DummyResponse(chunks=[b"data"], headers={"Content-Length": "4"})
    events = []

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: DummyClient(response))
    monkeypatch.setattr(DownloadRateMeter, "update", lambda self, current: 2048.0)

    HttpDownloader._download_stream(
        download_info=make_download_info(content=b"data"),
        path=tmp_path / "file.jar",
        timeout=20.0,
        reporter=ProgressReporter(events.append),
        progress_stage=ProgressStage.DOWNLOADING_CLIENT,
    )

    assert any(event.bytes_per_second == 2048.0 for event in events)


def test_download_stream_applies_shared_bandwidth_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    response = DummyResponse(chunks=[b"ab", b"cde"], headers={"Content-Length": "5"})
    throttled = []

    monkeypatch.setattr(HttpDownloader, "get_client", lambda: DummyClient(response))
    monkeypatch.setattr("src.core.network.httpx_downloader.download_bandwidth_limiter.throttle", lambda size: throttled.append(size))

    HttpDownloader._download_stream(download_info=make_download_info(content=b"abcde"), path=tmp_path / "file.jar", timeout=20.0)

    assert throttled == [2, 3]
