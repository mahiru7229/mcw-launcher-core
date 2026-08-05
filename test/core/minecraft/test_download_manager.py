import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.download_manager import DownloadClientManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.download import DownloadClient
from src.models.progress.progress_stage import ProgressStage


def make_version(
    path: Path,
    version_id: str = "1.20.1",
):
    return SimpleNamespace(
        id=version_id,
        path=path,
    )


def make_client_metadata(
    *,
    url: str = "https://example.com/client.jar",
    sha1: str = "abc123",
    size: int = 1024,
) -> dict:
    return {
        "downloads": {
            "client": {
                "url": url,
                "sha1": sha1,
                "size": size,
            }
        }
    }


def test_load_download_reads_valid_json(
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    expected = make_client_metadata()

    metadata_path.write_text(
        json.dumps(expected),
        encoding="utf-8",
    )

    result = DownloadClientManager._load_download(
        metadata_path
    )

    assert result == expected


def test_load_download_returns_empty_dict_for_invalid_json(
    tmp_path: Path,
):
    metadata_path = tmp_path / "invalid.json"
    metadata_path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    result = DownloadClientManager._load_download(
        metadata_path
    )

    assert result == {}


def test_load_download_returns_empty_dict_for_missing_file(
    tmp_path: Path,
):
    result = DownloadClientManager._load_download(
        tmp_path / "missing.json"
    )

    assert result == {}


def test_load_download_object_creates_download_client():
    metadata = make_client_metadata(
        url="https://example.com/1.20.1.jar",
        sha1="deadbeef",
        size=2048,
    )

    result = DownloadClientManager._load_download_object(
        metadata
    )

    assert isinstance(result, DownloadClient)
    assert result.url == (
        "https://example.com/1.20.1.jar"
    )
    assert result.sha1 == "deadbeef"
    assert result.size == 2048


def test_load_download_object_converts_size_to_int():
    metadata = make_client_metadata()
    metadata["downloads"]["client"]["size"] = "4096"

    result = DownloadClientManager._load_download_object(
        metadata
    )

    assert result.size == 4096
    assert isinstance(result.size, int)


@pytest.mark.parametrize(
    "missing_path",
    [
        ("downloads",),
        ("downloads", "client"),
        ("downloads", "client", "url"),
        ("downloads", "client", "sha1"),
        ("downloads", "client", "size"),
    ],
)
def test_load_download_object_raises_for_missing_required_metadata(
    missing_path: tuple[str, ...],
):
    metadata = make_client_metadata()

    target = metadata

    for key in missing_path[:-1]:
        target = target[key]

    target.pop(missing_path[-1])

    with pytest.raises(
        RuntimeError,
        match="Invalid Minecraft client download data",
    ):
        DownloadClientManager._load_download_object(
            metadata
        )


@pytest.mark.parametrize(
    "invalid_size",
    [
        None,
        "",
        "not-a-number",
        [],
        {},
    ],
)
def test_load_download_object_raises_for_invalid_size(
    invalid_size,
):
    metadata = make_client_metadata()
    metadata["downloads"]["client"]["size"] = invalid_size

    with pytest.raises(
        RuntimeError,
        match="Invalid Minecraft client download data",
    ):
        DownloadClientManager._load_download_object(
            metadata
        )


def test_load_returns_existing_client_when_sha1_is_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    client_path.parent.mkdir(parents=True)
    client_path.write_bytes(b"existing-client")

    version = make_version(metadata_path)
    client_obj = DownloadClient(
        url="https://example.com/client.jar",
        sha1="valid-sha1",
        size=15,
    )

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: client_obj,
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: True,
    )

    def fail_download(**kwargs):
        raise AssertionError(
            "download() must not be called for a valid cached client"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fail_download,
    )

    result = DownloadClientManager.load(version)

    assert result == client_path


def test_load_creates_version_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "missing-version-dir"
    client_path = client_dir / "client.jar"
    version = make_version(metadata_path)

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="sha1",
            size=1,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    assert not client_dir.exists()

    DownloadClientManager.load(version)

    assert client_dir.exists()
    assert client_dir.is_dir()


def test_load_deletes_existing_client_when_sha1_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    client_path.parent.mkdir(parents=True)
    client_path.write_bytes(b"broken-client")
    version = make_version(metadata_path)

    deleted_paths = []

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="expected-sha1",
            size=13,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "delete_file",
        lambda path: deleted_paths.append(path),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    DownloadClientManager.load(version)

    assert deleted_paths == [client_path]


def test_load_does_not_delete_missing_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    version = make_version(metadata_path)

    deleted_paths = []

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="expected-sha1",
            size=1,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "delete_file",
        lambda path: deleted_paths.append(path),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    DownloadClientManager.load(version)

    assert deleted_paths == []


def test_load_passes_expected_keyword_arguments_to_downloader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    version = make_version(
        metadata_path,
        version_id="1.20.1",
    )

    client_obj = DownloadClient(
        url="https://example.com/client.jar",
        sha1="sha1",
        size=1024,
    )
    reporter = object()
    received = {}

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: client_obj,
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )

    def fake_download(**kwargs):
        received.update(kwargs)
        return kwargs["path"]

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fake_download,
    )

    result = DownloadClientManager.load(
        version,
        reporter=reporter,
    )

    assert result == client_path
    assert received == {
        "download_info": client_obj,
        "path": client_path,
        "reporter": reporter,
        "progress_stage": (
            ProgressStage.DOWNLOADING_CLIENT
        ),
        "progress_message": (
            "Downloading Minecraft 1.20.1 client..."
        ),
    }


def test_load_returns_path_returned_by_downloader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    downloaded_path = tmp_path / "downloaded-client.jar"
    version = make_version(metadata_path)

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="sha1",
            size=1,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: downloaded_path,
    )

    result = DownloadClientManager.load(version)

    assert result == downloaded_path


def test_load_uses_version_metadata_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "custom-version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    version = make_version(metadata_path)
    received = {}

    def fake_load_download(path):
        received["metadata_path"] = path
        return make_client_metadata()

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        fake_load_download,
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="sha1",
            size=1,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    DownloadClientManager.load(version)

    assert received["metadata_path"] == metadata_path


def test_load_passes_none_reporter_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    metadata_path = tmp_path / "version.json"
    client_dir = tmp_path / "version"
    client_path = client_dir / "client.jar"
    version = make_version(metadata_path)
    received = {}

    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download",
        lambda path: make_client_metadata(),
    )
    monkeypatch.setattr(
        DownloadClientManager,
        "_load_download_object",
        lambda data: DownloadClient(
            url="https://example.com/client.jar",
            sha1="sha1",
            size=1,
        ),
    )
    monkeypatch.setattr(
        Paths,
        "version_dir",
        lambda version: client_dir,
    )
    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )

    def fake_download(**kwargs):
        received.update(kwargs)
        return kwargs["path"]

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fake_download,
    )

    DownloadClientManager.load(version)

    assert received["reporter"] is None