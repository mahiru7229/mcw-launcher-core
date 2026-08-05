import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.asset_index_manager import AssetIndexManager
from src.core.minecraft.asset_manager import (
    MAIN_LINK,
    MAX_WORKERS,
    AssetManager,
)
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.assets import DownloadAsset
from src.models.progress.progress_stage import ProgressStage


class DummyReporter:
    def __init__(self):
        self.events = []

    def files(
        self,
        *,
        stage,
        message,
        current,
        total,
    ):
        self.events.append(
            {
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
            }
        )


def make_version(
    version_id: str = "1.20.1",
):
    return SimpleNamespace(
        id=version_id,
        assets="5",
    )


def make_asset(
    *,
    logical_name: str = "minecraft/sounds/test.ogg",
    sha1: str = "abcdef1234567890",
    size: int = 1024,
) -> DownloadAsset:
    return DownloadAsset(
        logical_name=logical_name,
        url=(
            f"{MAIN_LINK}/"
            f"{sha1[:2]}/"
            f"{sha1}"
        ),
        sha1=sha1,
        size=size,
    )


def make_asset_index_data() -> dict:
    return {
        "objects": {
            "minecraft/sounds/test.ogg": {
                "hash": "abcdef1234567890",
                "size": 1024,
            },
            "minecraft/lang/en_us.json": {
                "hash": "1234567890abcdef",
                "size": 2048,
            },
        }
    }


def test_load_asset_index_reads_valid_json(
    tmp_path: Path,
):
    path = tmp_path / "index.json"
    expected = make_asset_index_data()

    path.write_text(
        json.dumps(expected),
        encoding="utf-8",
    )

    assert (
        AssetManager._load_asset_index(path)
        == expected
    )


def test_load_asset_index_returns_empty_dict_for_invalid_json(
    tmp_path: Path,
):
    path = tmp_path / "invalid.json"
    path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    assert (
        AssetManager._load_asset_index(path)
        == {}
    )


def test_load_asset_index_returns_empty_dict_for_missing_file(
    tmp_path: Path,
):
    assert (
        AssetManager._load_asset_index(
            tmp_path / "missing.json"
        )
        == {}
    )


def test_parse_assets_returns_download_asset_models():
    result = AssetManager._parse_assets(
        make_asset_index_data()
    )

    assert result == [
        DownloadAsset(
            logical_name=(
                "minecraft/sounds/test.ogg"
            ),
            url=(
                f"{MAIN_LINK}/ab/"
                "abcdef1234567890"
            ),
            sha1="abcdef1234567890",
            size=1024,
        ),
        DownloadAsset(
            logical_name=(
                "minecraft/lang/en_us.json"
            ),
            url=(
                f"{MAIN_LINK}/12/"
                "1234567890abcdef"
            ),
            sha1="1234567890abcdef",
            size=2048,
        ),
    ]


def test_parse_assets_converts_size_to_int():
    data = {
        "objects": {
            "minecraft/test.txt": {
                "hash": "abcdef1234567890",
                "size": "4096",
            }
        }
    }

    result = AssetManager._parse_assets(data)

    assert result[0].size == 4096
    assert isinstance(result[0].size, int)


def test_parse_assets_preserves_logical_order():
    data = {
        "objects": {
            "first": {
                "hash": "aa1111",
                "size": 1,
            },
            "second": {
                "hash": "bb2222",
                "size": 2,
            },
            "third": {
                "hash": "cc3333",
                "size": 3,
            },
        }
    }

    result = AssetManager._parse_assets(data)

    assert [
        asset.logical_name
        for asset in result
    ] == [
        "first",
        "second",
        "third",
    ]


def test_parse_assets_returns_empty_list_when_objects_missing():
    assert AssetManager._parse_assets({}) == []


def test_parse_assets_returns_empty_list_when_objects_empty():
    assert (
        AssetManager._parse_assets(
            {"objects": {}}
        )
        == []
    )


@pytest.mark.parametrize(
    "invalid_objects",
    [
        None,
        [],
        "invalid",
    ],
)
def test_parse_assets_raises_for_invalid_objects_structure(
    invalid_objects,
):
    with pytest.raises(
        AttributeError,
    ):
        AssetManager._parse_assets(
            {"objects": invalid_objects}
        )


@pytest.mark.parametrize(
    (
        "logical_name",
        "object_data",
    ),
    [
        (
            "missing-hash",
            {
                "size": 10,
            },
        ),
        (
            "missing-size",
            {
                "hash": "abcdef",
            },
        ),
        (
            "invalid-size",
            {
                "hash": "abcdef",
                "size": "not-a-number",
            },
        ),
        (
            "object-is-none",
            None,
        ),
    ],
)
def test_parse_assets_raises_for_invalid_asset_data(
    logical_name: str,
    object_data,
):
    with pytest.raises(
        RuntimeError,
        match=(
            f"Invalid asset data: "
            f"{logical_name}"
        ),
    ):
        AssetManager._parse_assets(
            {
                "objects": {
                    logical_name: object_data,
                }
            }
        )


@pytest.mark.parametrize(
    (
        "asset_hash",
        "expected",
    ),
    [
        (
            "abcdef1234567890",
            (
                f"{MAIN_LINK}/ab/"
                "abcdef1234567890"
            ),
        ),
        (
            "0011223344556677",
            (
                f"{MAIN_LINK}/00/"
                "0011223344556677"
            ),
        ),
        (
            "ffabcdef",
            (
                f"{MAIN_LINK}/ff/"
                "ffabcdef"
            ),
        ),
    ],
)
def test_build_download_url_uses_first_two_hash_characters(
    asset_hash: str,
    expected: str,
):
    assert (
        AssetManager._build_download_url(
            asset_hash
        )
        == expected
    )


def test_load_calls_asset_index_manager_with_reporter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    reporter = DummyReporter()
    index_path = tmp_path / "index.json"
    received = {}

    def fake_load(
        *,
        version,
        reporter,
    ):
        received["version"] = version
        received["reporter"] = reporter
        return index_path

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        fake_load,
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [],
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: tmp_path / "objects",
    )

    AssetManager.load(
        version,
        reporter=reporter,
    )

    assert received == {
        "version": version,
        "reporter": reporter,
    }

    assert reporter.events == [
        {
            "stage": ProgressStage.DOWNLOADING_ASSETS,
            "message": "Preparing Minecraft assets...",
            "current": 0,
            "total": 0,
        }
    ]


def test_load_returns_asset_objects_directory_when_no_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version()
    expected = tmp_path / "assets" / "objects"

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [],
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: expected,
    )

    result = AssetManager.load(version)

    assert result == expected


def test_load_reports_zero_progress_when_no_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    reporter = DummyReporter()

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [],
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: tmp_path / "objects",
    )

    AssetManager.load(
        make_version(),
        reporter=reporter,
    )

    assert reporter.events == [
        {
            "stage": (
                ProgressStage.DOWNLOADING_ASSETS
            ),
            "message": (
                "Preparing Minecraft assets..."
            ),
            "current": 0,
            "total": 0,
        }
    ]


def test_load_does_not_close_client_when_no_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    closed = []

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [],
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: tmp_path / "objects",
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: closed.append(True),
    )

    AssetManager.load(make_version())

    # Current implementation returns before try/finally.
    assert closed == []


def test_load_downloads_all_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    assets = [
        make_asset(
            logical_name="one",
            sha1="aa1111",
        ),
        make_asset(
            logical_name="two",
            sha1="bb2222",
        ),
        make_asset(
            logical_name="three",
            sha1="cc3333",
        ),
    ]
    objects_dir = tmp_path / "objects"
    closed = []

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: assets,
    )
    monkeypatch.setattr(
        AssetManager,
        "_download_single_asset",
        lambda asset: objects_dir / asset.sha1,
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: objects_dir,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: closed.append(True),
    )

    result = AssetManager.load(
        make_version()
    )

    assert result == objects_dir
    assert closed == []


def test_load_reports_initial_and_completed_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    assets = [
        make_asset(
            logical_name="one",
            sha1="aa1111",
        ),
        make_asset(
            logical_name="two",
            sha1="bb2222",
        ),
    ]
    reporter = DummyReporter()

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: assets,
    )
    monkeypatch.setattr(
        AssetManager,
        "_download_single_asset",
        lambda asset: tmp_path / asset.sha1,
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: tmp_path / "objects",
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: None,
    )

    AssetManager.load(
        make_version(),
        reporter=reporter,
    )

    assert reporter.events[0] == {
        "stage": (
            ProgressStage.DOWNLOADING_ASSETS
        ),
        "message": (
            "Preparing Minecraft assets..."
        ),
        "current": 0,
        "total": 2,
    }

    assert sorted(
        event["current"]
        for event in reporter.events[1:]
    ) == [
        1,
        2,
    ]

    assert all(
        event["total"] == 2
        for event in reporter.events
    )


def test_load_wraps_asset_error_and_keeps_shared_client_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset(
        logical_name="minecraft/broken.ogg",
        sha1="aa1111",
    )
    closed = []

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [asset],
    )

    def fail_download(asset):
        raise OSError("disk failure")

    monkeypatch.setattr(
        AssetManager,
        "_download_single_asset",
        fail_download,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: closed.append(True),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Failed to download asset: "
            "minecraft/broken.ogg"
        ),
    ) as error:
        AssetManager.load(
            make_version()
        )

    assert isinstance(
        error.value.__cause__,
        OSError,
    )
    assert closed == []


def test_load_uses_configured_worker_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset()
    received = {}

    class FakeFuture:
        def __init__(
            self,
            function,
            *args,
        ):
            self._function = function
            self._args = args

        def result(self):
            return self._function(
                *self._args
            )

    class FakeExecutor:
        def __init__(
            self,
            max_workers,
        ):
            received["max_workers"] = max_workers

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def submit(
            self,
            function,
            *args,
        ):
            return FakeFuture(
                function,
                *args,
            )

    monkeypatch.setattr(
        AssetIndexManager,
        "load",
        lambda **kwargs: tmp_path / "index.json",
    )
    monkeypatch.setattr(
        AssetManager,
        "_load_asset_index",
        lambda path: {},
    )
    monkeypatch.setattr(
        AssetManager,
        "_parse_assets",
        lambda data: [asset],
    )
    monkeypatch.setattr(
        AssetManager,
        "_download_single_asset",
        lambda asset: tmp_path / asset.sha1,
    )
    monkeypatch.setattr(
        "src.core.minecraft.asset_manager.concurrent.futures.ThreadPoolExecutor",
        FakeExecutor,
    )
    monkeypatch.setattr(
        "src.core.minecraft.asset_manager.concurrent.futures.as_completed",
        lambda futures: list(futures),
    )
    monkeypatch.setattr(
        Paths,
        "asset_index_dir",
        lambda: tmp_path / "objects",
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: None,
    )

    AssetManager.load(make_version())

    assert received["max_workers"] == MAX_WORKERS


def test_download_single_asset_returns_valid_cached_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset()
    asset_path = tmp_path / asset.sha1
    asset_path.write_bytes(b"cached")

    monkeypatch.setattr(
        Paths,
        "asset_object",
        lambda asset: asset_path,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: True,
    )

    def fail_download(**kwargs):
        raise AssertionError(
            "valid cached asset must not download"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fail_download,
    )

    assert (
        AssetManager._download_single_asset(
            asset
        )
        == asset_path
    )


def test_download_single_asset_deletes_invalid_cached_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset()
    asset_path = tmp_path / asset.sha1
    asset_path.write_bytes(b"broken")
    deleted = []

    monkeypatch.setattr(
        Paths,
        "asset_object",
        lambda asset: asset_path,
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

    AssetManager._download_single_asset(asset)

    assert deleted == [asset_path]


def test_download_single_asset_deletes_missing_target_safely(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset()
    asset_path = tmp_path / asset.sha1
    deleted = []

    monkeypatch.setattr(
        Paths,
        "asset_object",
        lambda asset: asset_path,
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

    AssetManager._download_single_asset(asset)

    # Current implementation always delegates safety
    # to HttpDownloader.delete_file().
    assert deleted == [asset_path]


def test_download_single_asset_calls_downloader_with_retry_five(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    asset = make_asset()
    asset_path = tmp_path / asset.sha1
    received = {}

    monkeypatch.setattr(
        Paths,
        "asset_object",
        lambda asset: asset_path,
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

    result = (
        AssetManager._download_single_asset(
            asset
        )
    )

    assert result == asset_path
    assert received == {
        "download_info": asset,
        "path": asset_path,
        "max_retry": 5,
    }