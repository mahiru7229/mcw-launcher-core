from pathlib import Path
import hashlib

import pytest

from src.core.modrinth.modrinth_downloader import ModrinthDownloader


def test_verify_checks_sha1_sha512_and_size(tmp_path: Path):
    path = tmp_path / "file.jar"
    content = b"modrinth-test"
    path.write_bytes(content)

    assert ModrinthDownloader.verify(path, sha1=hashlib.sha1(content).hexdigest(), sha512=hashlib.sha512(content).hexdigest(), expected_size=len(content))
    assert not ModrinthDownloader.verify(path, sha1="0" * 40)


def test_pack_urls_require_https_and_allowed_hosts():
    with pytest.raises(RuntimeError, match="HTTPS"):
        ModrinthDownloader._validate_pack_url("http://cdn.modrinth.com/file.jar")
    with pytest.raises(RuntimeError, match="not allowed"):
        ModrinthDownloader._validate_pack_url("https://example.com/file.jar")

    ModrinthDownloader._validate_pack_url("https://cdn.modrinth.com/data/project/file.jar")


def test_download_resumes_partial_file_and_reports_progress(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader
    from src.core.progress.progress_reporter import ProgressReporter
    from src.models.progress.progress_stage import ProgressStage

    content = b"abcdef"
    destination = tmp_path / "example.jar"
    destination.with_name(destination.name + ".part").write_bytes(content[:3])
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers.get("Range") == "bytes=3-"
        return httpx.Response(206, headers={"Content-Length": "3", "Content-Range": "bytes 3-5/6"}, content=content[3:])

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)
    events = []

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        reporter=ProgressReporter(events.append),
        progress_stage=ProgressStage.DOWNLOADING_MODS,
    )

    assert result.read_bytes() == content
    assert len(requests) == 1
    assert events[0].current == 3
    assert events[0].total == 6
    assert events[-1].percentage == 100


def test_download_skips_rejected_source_and_tries_next_url(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"fallback-source"
    destination = tmp_path / "example.jar"
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://untrusted.example/file.jar", "https://cdn.modrinth.com/data/project/example.jar"),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        restrict_hosts=True,
        max_retry=1,
    )

    assert result.read_bytes() == content
    assert requests == ["https://cdn.modrinth.com/data/project/example.jar"]



def test_download_restarts_full_after_range_not_satisfiable(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"abcdef"
    destination = tmp_path / "example.jar"
    destination.with_name(destination.name + ".part").write_bytes(content[:3])
    received_ranges = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_ranges.append(request.headers.get("Range"))
        if len(received_ranges) == 1:
            return httpx.Response(416, headers={"Content-Range": "bytes */6"})
        return httpx.Response(200, headers={"Content-Length": "6"}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        max_retry=1,
    )

    assert result.read_bytes() == content
    assert received_ranges == ["bytes=3-", None]


def test_download_restarts_full_after_invalid_content_range(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"abcdef"
    destination = tmp_path / "example.jar"
    destination.with_name(destination.name + ".part").write_bytes(content[:3])
    received_ranges = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_ranges.append(request.headers.get("Range"))
        if len(received_ranges) == 1:
            return httpx.Response(206, headers={"Content-Length": "3", "Content-Range": "bytes 0-2/6"}, content=b"abc")
        return httpx.Response(200, headers={"Content-Length": "6"}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        max_retry=1,
    )

    assert result.read_bytes() == content
    assert received_ranges == ["bytes=3-", None]


def test_download_accepts_full_response_when_server_ignores_range(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"abcdef"
    destination = tmp_path / "example.jar"
    destination.with_name(destination.name + ".part").write_bytes(content[:3])
    received_ranges = []

    def handler(request: httpx.Request) -> httpx.Response:
        received_ranges.append(request.headers.get("Range"))
        return httpx.Response(200, headers={"Content-Length": "6"}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        max_retry=1,
    )

    assert result.read_bytes() == content
    assert received_ranges == ["bytes=3-"]


def test_download_uses_next_url_after_non_retryable_http_error(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"fallback"
    destination = tmp_path / "example.jar"
    requested_hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_hosts.append(request.url.host)
        if request.url.host == "cdn.modrinth.com":
            return httpx.Response(403)
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar", "https://github.com/example/example.jar"),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        max_retry=1,
    )

    assert result.read_bytes() == content
    assert requested_hosts == ["cdn.modrinth.com", "github.com"]


def test_force_download_discards_valid_partial_file(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    old_content = b"old-content"
    new_content = b"new-content"
    destination = tmp_path / "example.jar"
    destination.with_name(destination.name + ".part").write_bytes(old_content)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.headers.get("Range"))
        return httpx.Response(200, headers={"Content-Length": str(len(new_content))}, content=new_content)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    monkeypatch.setattr(HttpDownloader, "_client", client)

    result = ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(new_content).hexdigest(),
        sha512=hashlib.sha512(new_content).hexdigest(),
        expected_size=len(new_content),
        force=True,
        max_retry=1,
    )

    assert result.read_bytes() == new_content
    assert requests == [None]


def test_modrinth_download_uses_shared_bandwidth_limiter(tmp_path, monkeypatch):
    import httpx

    from src.core.network.httpx_downloader import HttpDownloader

    content = b"limited-mod"
    destination = tmp_path / "example.jar"
    throttled = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": str(len(content))}, content=content)

    monkeypatch.setattr(HttpDownloader, "_client", httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True))
    monkeypatch.setattr("src.core.modrinth.modrinth_downloader.download_bandwidth_limiter.throttle", lambda size: throttled.append(size))

    ModrinthDownloader.download_urls(
        urls=("https://cdn.modrinth.com/data/project/example.jar",),
        destination=destination,
        sha1=hashlib.sha1(content).hexdigest(),
        sha512=hashlib.sha512(content).hexdigest(),
        expected_size=len(content),
        max_retry=1,
    )

    assert destination.read_bytes() == content
    assert sum(throttled) == len(content)
