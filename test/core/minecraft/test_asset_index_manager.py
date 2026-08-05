from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.asset_index_manager import AssetIndexManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.assets_index import DownloadAssetIndex
from src.models.progress.progress_stage import ProgressStage


def make_version(
    *,
    version_id: str = "1.20.1",
    assets: str = "5",
    asset_index: dict | None = None,
):
    return SimpleNamespace(
        id=version_id,
        assets=assets,
        asset_index=asset_index
        or {
            "id": assets,
            "url": "https://example.com/assets.json",
            "sha1": "abc123",
            "size": 2048,
        },
    )


def test_parse_assets_index_returns_model():
    version = make_version()

    result = AssetIndexManager._parse_assets_index(
        version
    )

    assert isinstance(result, DownloadAssetIndex)
    assert result.id == "5"
    assert result.url == (
        "https://example.com/assets.json"
    )
    assert result.sha1 == "abc123"
    assert result.size == 2048


def test_parse_assets_index_converts_size_to_int():
    version = make_version(
        asset_index={
            "id": "5",
            "url": "https://example.com/assets.json",
            "sha1": "abc123",
            "size": "4096",
        }
    )

    result = AssetIndexManager._parse_assets_index(
        version
    )

    assert result.size == 4096
    assert isinstance(result.size, int)


@pytest.mark.parametrize(
    "missing_key",
    [
        "id",
        "url",
        "sha1",
        "size",
    ],
)
def test_parse_assets_index_raises_for_missing_required_field(
    missing_key: str,
):
    data = {
        "id": "5",
        "url": "https://example.com/assets.json",
        "sha1": "abc123",
        "size": 2048,
    }
    data.pop(missing_key)

    version = make_version(
        asset_index=data
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Invalid asset index data for "
            "Minecraft 1.20.1"
        ),
    ):
        AssetIndexManager._parse_assets_index(
            version
        )


@pytest.mark.parametrize(
    "asset_index",
    [
        None,
        {},
        [],
        "invalid",
    ],
)
def test_parse_assets_index_raises_for_invalid_structure(
    asset_index,
):
    version = SimpleNamespace(
        id="1.20.1",
        assets="5",
        asset_index=asset_index,
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Invalid asset index data for "
            "Minecraft 1.20.1"
        ),
    ):
        AssetIndexManager._parse_assets_index(
            version
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
def test_parse_assets_index_raises_for_invalid_size(
    invalid_size,
):
    version = make_version(
        asset_index={
            "id": "5",
            "url": "https://example.com/assets.json",
            "sha1": "abc123",
            "size": invalid_size,
        }
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Invalid asset index data for "
            "Minecraft 1.20.1"
        ),
    ):
        AssetIndexManager._parse_assets_index(
            version
        )


def test_load_returns_cached_asset_index_when_sha1_is_valid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    asset_index_path = (
        tmp_path
        / "assets"
        / "indexes"
        / "5.json"
    )
    asset_index_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    asset_index_path.write_bytes(
        b"cached-index"
    )

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: asset_index_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: True,
    )

    def fail_download(**kwargs):
        raise AssertionError(
            "valid asset index must not download"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fail_download,
    )

    result = AssetIndexManager.load(
        version
    )

    assert result == asset_index_path


def test_load_deletes_invalid_cached_asset_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    asset_index_path = tmp_path / "5.json"
    asset_index_path.write_bytes(
        b"broken-index"
    )
    deleted = []

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: asset_index_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "delete_file",
        lambda path: deleted.append(path),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    AssetIndexManager.load(version)

    assert deleted == [asset_index_path]


def test_load_does_not_delete_missing_asset_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    asset_index_path = tmp_path / "5.json"
    deleted = []

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: asset_index_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "delete_file",
        lambda path: deleted.append(path),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: kwargs["path"],
    )

    AssetIndexManager.load(version)

    assert deleted == []


def test_load_passes_expected_keyword_arguments_to_downloader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        version_id="1.20.1",
        assets="5",
    )
    asset_index_path = tmp_path / "5.json"
    reporter = object()
    parsed = DownloadAssetIndex(
        id="5",
        url="https://example.com/assets.json",
        sha1="abc123",
        size=2048,
    )
    received = {}

    monkeypatch.setattr(
        AssetIndexManager,
        "_parse_assets_index",
        lambda version: parsed,
    )
    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: asset_index_path,
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

    result = AssetIndexManager.load(
        version,
        reporter=reporter,
    )

    assert result == asset_index_path
    assert received == {
        "download_info": parsed,
        "path": asset_index_path,
        "max_retry": 2,
        "timeout": 20.0,
        "reporter": reporter,
        "progress_stage": (
            ProgressStage.DOWNLOADING_ASSET_INDEX
        ),
        "progress_message": (
            "Downloading asset index 5.json..."
        ),
    }


def test_load_passes_none_reporter_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    asset_index_path = tmp_path / "5.json"
    received = {}

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: asset_index_path,
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

    AssetIndexManager.load(version)

    assert received["reporter"] is None


def test_load_uses_assets_id_in_progress_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        assets="legacy",
        asset_index={
            "id": "legacy",
            "url": "https://example.com/legacy.json",
            "sha1": "sha1",
            "size": 10,
        },
    )
    received = {}

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: tmp_path / "legacy.json",
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

    AssetIndexManager.load(version)

    assert received["progress_message"] == (
        "Downloading asset index legacy.json..."
    )


def test_load_returns_path_returned_by_downloader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    expected_path = (
        tmp_path
        / "downloaded"
        / "asset-index.json"
    )

    monkeypatch.setattr(
        Paths,
        "asset_index",
        lambda version: tmp_path / "5.json",
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: False,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "download",
        lambda **kwargs: expected_path,
    )

    result = AssetIndexManager.load(version)

    assert result == expected_path