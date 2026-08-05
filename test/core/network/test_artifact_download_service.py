from __future__ import annotations

from hashlib import sha1, sha512
from pathlib import Path
import errno
import socket
import ssl

import httpx
import pytest

from src.core.network.artifact_download_service import ArtifactDownloadError, ArtifactDownloadService, ArtifactManualValidationError
from src.core.network.download_pause import DownloadCancelledError, download_pause_controller
from src.core.network.network_errors import DownloadChecksumMismatchError, DownloadSizeMismatchError, DownloadValidationError
from src.models.network.artifact import ArtifactRequest, DownloadFailureReason


def request(tmp_path: Path, **overrides) -> ArtifactRequest:
    values = dict(provider="modrinth", purpose="modpack-artifact", destination=tmp_path / "expected.zip", urls=("https://cdn.modrinth.com/expected.zip",), expected_filename="expected.zip")
    values.update(overrides)
    return ArtifactRequest(**values)


@pytest.mark.parametrize(
    ("error", "reason", "status"),
    [
        (DownloadValidationError("No download URL is available."), DownloadFailureReason.NO_DOWNLOAD_URL, None),
        (httpx.ConnectTimeout("connect timeout"), DownloadFailureReason.CONNECT_TIMEOUT, None),
        (httpx.ReadTimeout("read timeout"), DownloadFailureReason.READ_TIMEOUT, None),
        (socket.gaierror("dns"), DownloadFailureReason.DNS_ERROR, None),
        (ssl.SSLError("tls"), DownloadFailureReason.TLS_ERROR, None),
        (ConnectionResetError("reset"), DownloadFailureReason.CONNECTION_RESET, None),
        (DownloadSizeMismatchError("size mismatch"), DownloadFailureReason.SIZE_MISMATCH, None),
        (DownloadChecksumMismatchError("expected.zip", "sha1"), DownloadFailureReason.HASH_MISMATCH, None),
        (OSError(errno.EACCES, "permission denied"), DownloadFailureReason.FILE_ACCESS_ERROR, None),
        (OSError(errno.ENOSPC, "disk full"), DownloadFailureReason.DISK_SPACE_ERROR, None),
    ],
)
def test_classifies_structured_failures(tmp_path: Path, error: Exception, reason: DownloadFailureReason, status: int | None) -> None:
    failure = ArtifactDownloadService().failure(request(tmp_path), error)
    assert failure.reason is reason
    assert failure.http_status == status


@pytest.mark.parametrize(
    ("status", "reason", "retryable"),
    [
        (403, DownloadFailureReason.HTTP_403, False),
        (404, DownloadFailureReason.HTTP_404, False),
        (429, DownloadFailureReason.HTTP_429, True),
        (503, DownloadFailureReason.HTTP_5XX, True),
    ],
)
def test_classifies_http_status(tmp_path: Path, status: int, reason: DownloadFailureReason, retryable: bool) -> None:
    http_request = httpx.Request("GET", "https://cdn.modrinth.com/file")
    response = httpx.Response(status, request=http_request)
    error = httpx.HTTPStatusError("failed", request=http_request, response=response)
    failure = ArtifactDownloadService().failure(request(tmp_path), error)
    assert failure.reason is reason
    assert failure.http_status == status
    assert failure.retryable is retryable


def test_no_url_raises_structured_error(tmp_path: Path) -> None:
    with pytest.raises(ArtifactDownloadError) as captured:
        ArtifactDownloadService().download(request(tmp_path, urls=()))
    assert captured.value.failure.reason is DownloadFailureReason.NO_DOWNLOAD_URL


def test_manual_file_with_different_name_and_extension_is_accepted_by_hash(tmp_path: Path) -> None:
    content = b"manifest-managed zip artifact"
    source = tmp_path / "browser-renamed.jar"
    source.write_bytes(content)
    destination = tmp_path / "mods" / "expected.zip"
    artifact = request(
        tmp_path,
        destination=destination,
        expected_filename="expected.zip",
        expected_size=len(content),
        hashes={"sha1": sha1(content, usedforsecurity=False).hexdigest(), "sha512": sha512(content).hexdigest()},
    )

    installed = ArtifactDownloadService().accept_manual_file(artifact, source)

    assert installed == destination
    assert destination.read_bytes() == content
    assert not destination.with_name(destination.name + ".part").exists()


def test_manual_file_wrong_hash_uses_expected_artifact_message(tmp_path: Path) -> None:
    source = tmp_path / "wrong.bin"
    source.write_bytes(b"wrong")
    artifact = request(tmp_path, expected_size=5, hashes={"sha1": "0" * 40})
    with pytest.raises(ArtifactManualValidationError, match="Expected: expected.zip"):
        ArtifactDownloadService().verify_manual_file(artifact, source)


@pytest.mark.parametrize("path", ("../escape.jar", "/absolute.jar", "C:/absolute.jar", "mods/../escape.jar"))
def test_safe_destination_rejects_unsafe_paths(tmp_path: Path, path: str) -> None:
    with pytest.raises(RuntimeError, match="Unsafe"):
        ArtifactDownloadService.safe_destination(tmp_path, path)


def test_cancelled_manual_copy_removes_partial_file(tmp_path: Path) -> None:
    content = b"cancelled"
    source = tmp_path / "source.bin"
    source.write_bytes(content)
    destination = tmp_path / "mods" / "expected.zip"
    artifact = request(tmp_path, destination=destination, expected_size=len(content), hashes={"sha1": sha1(content, usedforsecurity=False).hexdigest()})
    download_pause_controller.begin()
    download_pause_controller.request_cancel()
    try:
        with pytest.raises(DownloadCancelledError):
            ArtifactDownloadService().accept_manual_file(artifact, source)
    finally:
        download_pause_controller.finish()
    assert not destination.exists()
    assert not destination.with_name(destination.name + ".part").exists()
