import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.library_manager import (
    MAX_WORKERS,
    DownloadLibraryManager,
)
from src.core.minecraft.library_rule_manager import LibraryRuleManager
from src.core.network.httpx_downloader import HttpDownloader
from src.models.minecraft.library import DownloadLibrary
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
    path: Path,
    version_id: str = "1.20.1",
):
    return SimpleNamespace(
        id=version_id,
        path=path,
    )


def make_library(
    *,
    path: str = "com/example/library.jar",
    url: str = "https://example.com/library.jar",
    sha1: str = "abc123",
    size: int = 1024,
    is_native: bool = False,
) -> DownloadLibrary:
    return DownloadLibrary(
        url=url,
        sha1=sha1,
        size=size,
        path=Path(path),
        is_native=is_native,
    )


def make_library_metadata() -> dict:
    return {
        "libraries": [
            {
                "name": "com.example:normal:1.0",
                "downloads": {
                    "artifact": {
                        "url": "https://example.com/normal.jar",
                        "sha1": "a" * 40,
                        "size": 100,
                        "path": "com/example/normal/1.0/normal-1.0.jar",
                    }
                },
            }
        ]
    }


def test_load_download_reads_valid_json(
    tmp_path: Path,
):
    path = tmp_path / "version.json"
    expected = make_library_metadata()

    path.write_text(
        json.dumps(expected),
        encoding="utf-8",
    )

    assert (
        DownloadLibraryManager._load_download(path)
        == expected
    )


def test_load_download_returns_empty_dict_for_invalid_json(
    tmp_path: Path,
):
    path = tmp_path / "invalid.json"
    path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    assert (
        DownloadLibraryManager._load_download(path)
        == {}
    )


def test_load_download_returns_empty_dict_for_missing_file(
    tmp_path: Path,
):
    assert (
        DownloadLibraryManager._load_download(
            tmp_path / "missing.json"
        )
        == {}
    )


def test_load_download_object_parses_artifact(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    result = (
        DownloadLibraryManager._load_download_object(
            make_library_metadata()
        )
    )

    assert result == [
        DownloadLibrary(
            url="https://example.com/normal.jar",
            sha1="a" * 40,
            size=100,
            path=Path(
                "com/example/normal/1.0/normal-1.0.jar"
            ),
            is_native=False,
        )
    ]


def test_load_download_object_converts_artifact_size_to_int(
    monkeypatch: pytest.MonkeyPatch,
):
    data = make_library_metadata()
    data["libraries"][0]["downloads"][
        "artifact"
    ]["size"] = "2048"

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    result = (
        DownloadLibraryManager._load_download_object(
            data
        )
    )

    assert result[0].size == 2048
    assert isinstance(result[0].size, int)


def test_load_download_object_skips_disallowed_library(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: False,
    )

    assert (
        DownloadLibraryManager._load_download_object(
            make_library_metadata()
        )
        == []
    )


def test_load_download_object_calls_rule_manager_for_every_library(
    monkeypatch: pytest.MonkeyPatch,
):
    libraries = [
        {
            "name": "first",
            "downloads": {},
        },
        {
            "name": "second",
            "downloads": {},
        },
    ]
    received = []

    def fake_is_allowed(library):
        received.append(library)
        return True

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        fake_is_allowed,
    )

    DownloadLibraryManager._load_download_object(
        {"libraries": libraries}
    )

    assert received == libraries


def test_load_download_object_parses_windows_native(
    monkeypatch: pytest.MonkeyPatch,
):
    data = {
        "libraries": [
            {
                "name": "org.lwjgl:lwjgl:3.3.1",
                "natives": {
                    "windows": "natives-windows",
                },
                "downloads": {
                    "classifiers": {
                        "natives-windows": {
                            "url": "https://example.com/native.jar",
                            "sha1": "b" * 40,
                            "size": 300,
                            "path": "org/lwjgl/native.jar",
                        }
                    }
                },
            }
        ]
    }

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )
    monkeypatch.setattr(LibraryRuleManager, "_get_current_os", lambda: "windows")

    result = (
        DownloadLibraryManager._load_download_object(
            data
        )
    )

    assert result == [
        DownloadLibrary(
            url="https://example.com/native.jar",
            sha1="b" * 40,
            size=300,
            path=Path("org/lwjgl/native.jar"),
            is_native=True,
        )
    ]


def test_load_download_object_replaces_native_arch_placeholder(
    monkeypatch: pytest.MonkeyPatch,
):
    data = {
        "libraries": [
            {
                "natives": {
                    "windows": "natives-windows-${arch}",
                },
                "downloads": {
                    "classifiers": {
                        "natives-windows-64": {
                            "url": "https://example.com/native64.jar",
                            "sha1": "c" * 40,
                            "size": 64,
                            "path": "native64.jar",
                        }
                    }
                },
            }
        ]
    }

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )
    monkeypatch.setattr(LibraryRuleManager, "_get_current_os", lambda: "windows")
    monkeypatch.setattr(LibraryRuleManager, "_get_current_arch", lambda: "x64")

    result = (
        DownloadLibraryManager._load_download_object(
            data
        )
    )

    assert len(result) == 1
    assert result[0].path == Path("native64.jar")
    assert result[0].is_native is True


def test_load_download_object_adds_artifact_before_native(
    monkeypatch: pytest.MonkeyPatch,
):
    data = {
        "libraries": [
            {
                "natives": {
                    "windows": "natives-windows",
                },
                "downloads": {
                    "artifact": {
                        "url": "https://example.com/artifact.jar",
                        "sha1": "d" * 40,
                        "size": 100,
                        "path": "artifact.jar",
                    },
                    "classifiers": {
                        "natives-windows": {
                            "url": "https://example.com/native.jar",
                            "sha1": "e" * 40,
                            "size": 200,
                            "path": "native.jar",
                        }
                    },
                },
            }
        ]
    }

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )
    monkeypatch.setattr(LibraryRuleManager, "_get_current_os", lambda: "windows")

    result = DownloadLibraryManager._load_download_object(data)

    assert [library.is_native for library in result] == [False, True]


def test_load_download_object_selects_linux_native(
    monkeypatch: pytest.MonkeyPatch,
):
    data = {
        "libraries": [
            {
                "natives": {"windows": "native-win", "linux": "native-linux"},
                "downloads": {
                    "classifiers": {
                        "native-linux": {
                            "url": "https://example.com/native-linux.jar",
                            "sha1": "f" * 40,
                            "size": 300,
                            "path": "org/lwjgl/native-linux.jar",
                        }
                    }
                },
            }
        ]
    }
    monkeypatch.setattr(LibraryRuleManager, "is_allowed", lambda _library: True)
    monkeypatch.setattr(LibraryRuleManager, "_get_current_os", lambda: "linux")

    result = DownloadLibraryManager._load_download_object(data)

    assert len(result) == 1
    assert result[0].path == Path("org/lwjgl/native-linux.jar")
    assert result[0].is_native is True


def test_load_download_object_skips_missing_native_classifier(
    monkeypatch: pytest.MonkeyPatch,
):
    data = {
        "libraries": [
            {
                "natives": {
                    "windows": "natives-windows",
                },
                "downloads": {
                    "classifiers": {},
                },
            }
        ]
    }

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    assert (
        DownloadLibraryManager._load_download_object(
            data
        )
        == []
    )


def test_load_returns_empty_list_and_reports_zero_when_no_libraries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    reporter = DummyReporter()
    version = make_version(
        tmp_path / "version.json"
    )
    closed = []

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download",
        lambda path: {"libraries": []},
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download_object",
        lambda data: [],
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: closed.append(True),
    )

    result = DownloadLibraryManager.load(
        version,
        reporter=reporter,
    )

    assert result == []
    assert reporter.events == [
        {
            "stage": (
                ProgressStage.DOWNLOADING_LIBRARIES
            ),
            "message": (
                "Preparing Minecraft libraries..."
            ),
            "current": 0,
            "total": 0,
        }
    ]

    # Current implementation returns before try/finally.
    assert closed == []


def test_load_downloads_all_libraries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        tmp_path / "version.json"
    )
    libraries = [
        make_library(path="one.jar"),
        make_library(path="two.jar"),
        make_library(path="three.jar"),
    ]
    closed = []

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download",
        lambda path: {},
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download_object",
        lambda data: libraries,
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_download_single_library",
        lambda library, version: (
            tmp_path / library.path
        ),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: closed.append(True),
    )

    result = DownloadLibraryManager.load(
        version
    )

    assert set(result) == {
        tmp_path / "one.jar",
        tmp_path / "two.jar",
        tmp_path / "three.jar",
    }
    assert closed == []


def test_load_reports_initial_and_completed_progress(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        tmp_path / "version.json"
    )
    libraries = [
        make_library(path="one.jar"),
        make_library(path="two.jar"),
    ]
    reporter = DummyReporter()

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download",
        lambda path: {},
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download_object",
        lambda data: libraries,
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_download_single_library",
        lambda library, version: (
            tmp_path / library.path
        ),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: None,
    )

    DownloadLibraryManager.load(
        version,
        reporter=reporter,
    )

    assert reporter.events[0] == {
        "stage": (
            ProgressStage.DOWNLOADING_LIBRARIES
        ),
        "message": (
            "Preparing Minecraft libraries..."
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


def test_load_wraps_library_error_and_keeps_shared_client_open(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        tmp_path / "version.json"
    )
    library = make_library(
        path="broken.jar"
    )
    closed = []

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download",
        lambda path: {},
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download_object",
        lambda data: [library],
    )

    def fail_download(*args, **kwargs):
        raise OSError("disk failure")

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_download_single_library",
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
            "Failed to download library: "
            "broken.jar"
        ),
    ) as error:
        DownloadLibraryManager.load(
            version
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
    version = make_version(
        tmp_path / "version.json"
    )
    library = make_library()
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
        DownloadLibraryManager,
        "_load_download",
        lambda path: {},
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_load_download_object",
        lambda data: [library],
    )
    monkeypatch.setattr(
        DownloadLibraryManager,
        "_download_single_library",
        lambda library, version: (
            tmp_path / library.path
        ),
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_manager.concurrent.futures.ThreadPoolExecutor",
        FakeExecutor,
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_manager.concurrent.futures.as_completed",
        lambda futures: list(futures),
    )
    monkeypatch.setattr(
        HttpDownloader,
        "close_client",
        lambda: None,
    )

    DownloadLibraryManager.load(
        version
    )

    assert received["max_workers"] == MAX_WORKERS


def test_download_single_library_returns_valid_cached_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries_root = tmp_path / "libraries"
    library = make_library(
        path="cached.jar",
    )
    library_path = (
        libraries_root / library.path
    )
    library_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    library_path.write_bytes(b"cached")

    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_root,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: True,
    )

    def fail_download(**kwargs):
        raise AssertionError(
            "valid cached library must not download"
        )

    monkeypatch.setattr(
        HttpDownloader,
        "download",
        fail_download,
    )

    result = (
        DownloadLibraryManager._download_single_library(
            library,
            make_version(tmp_path / "version.json"),
        )
    )

    assert result == library_path


def test_download_single_library_extracts_cached_native(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries_root = tmp_path / "libraries"
    library = make_library(
        path="native.jar",
        is_native=True,
    )
    library_path = (
        libraries_root / library.path
    )
    library_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    library_path.write_bytes(b"native")
    received = {}

    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_root,
    )
    monkeypatch.setattr(
        HttpDownloader,
        "verify_sha1",
        lambda path, sha1: True,
    )

    def fake_extract(
        *,
        native_path,
        version,
        sha1,
    ):
        received.update(
            {
                "native_path": native_path,
                "version": version,
                "sha1": sha1,
            }
        )

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_extract_native",
        fake_extract,
    )

    version = make_version(
        tmp_path / "version.json"
    )

    result = (
        DownloadLibraryManager._download_single_library(
            library,
            version,
        )
    )

    assert result == library_path
    assert received == {
        "native_path": library_path,
        "version": version,
        "sha1": library.sha1,
    }


def test_download_single_library_deletes_invalid_cached_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries_root = tmp_path / "libraries"
    library = make_library(
        path="broken.jar",
    )
    library_path = (
        libraries_root / library.path
    )
    library_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    library_path.write_bytes(b"broken")
    deleted = []

    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_root,
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

    DownloadLibraryManager._download_single_library(
        library,
        make_version(tmp_path / "version.json"),
    )

    assert deleted == [library_path]


def test_download_single_library_calls_downloader_with_retry_five(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries_root = tmp_path / "libraries"
    library = make_library(
        path="download.jar",
    )
    received = {}

    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_root,
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
        DownloadLibraryManager._download_single_library(
            library,
            make_version(tmp_path / "version.json"),
        )
    )

    expected_path = (
        libraries_root / library.path
    )

    assert result == expected_path
    assert received == {
        "download_info": library,
        "path": expected_path,
        "max_retry": 5,
    }


def test_download_single_library_extracts_downloaded_native(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries_root = tmp_path / "libraries"
    library = make_library(
        path="native.jar",
        is_native=True,
    )
    downloaded_path = (
        tmp_path / "downloaded-native.jar"
    )
    received = {}

    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_root,
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

    def fake_extract(
        *,
        native_path,
        version,
        sha1,
    ):
        received.update(
            {
                "native_path": native_path,
                "version": version,
                "sha1": sha1,
            }
        )

    monkeypatch.setattr(
        DownloadLibraryManager,
        "_extract_native",
        fake_extract,
    )

    version = make_version(
        tmp_path / "version.json"
    )

    result = (
        DownloadLibraryManager._download_single_library(
            library,
            version,
        )
    )

    assert result == downloaded_path
    assert received == {
        "native_path": downloaded_path,
        "version": version,
        "sha1": library.sha1,
    }


def test_extract_native_skips_meta_inf_and_creates_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        tmp_path / "version.json"
    )
    native_zip = tmp_path / "native.jar"
    destination = tmp_path / "natives"

    with zipfile.ZipFile(
        native_zip,
        "w",
    ) as archive:
        archive.writestr(
            "native.dll",
            b"native-data",
        )
        archive.writestr(
            "folder/extra.dll",
            b"extra-data",
        )
        archive.writestr(
            "META-INF/MANIFEST.MF",
            b"ignored",
        )

    monkeypatch.setattr(
        Paths,
        "natives",
        lambda version: destination,
    )

    DownloadLibraryManager._extract_native(
        native_path=native_zip,
        version=version,
        sha1="native-sha1",
    )

    assert (
        destination / "native.dll"
    ).read_bytes() == b"native-data"
    assert (
        destination / "folder" / "extra.dll"
    ).read_bytes() == b"extra-data"
    assert not (
        destination
        / "META-INF"
        / "MANIFEST.MF"
    ).exists()
    assert (
        destination
        / ".extracted"
        / "native-sha1"
    ).exists()


def test_extract_native_does_nothing_when_marker_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    version = make_version(
        tmp_path / "version.json"
    )
    native_zip = tmp_path / "native.jar"
    destination = tmp_path / "natives"
    marker = (
        destination
        / ".extracted"
        / "native-sha1"
    )
    marker.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    marker.touch()

    with zipfile.ZipFile(
        native_zip,
        "w",
    ) as archive:
        archive.writestr(
            "new-native.dll",
            b"must-not-extract",
        )

    monkeypatch.setattr(
        Paths,
        "natives",
        lambda version: destination,
    )

    DownloadLibraryManager._extract_native(
        native_path=native_zip,
        version=version,
        sha1="native-sha1",
    )

    assert not (
        destination / "new-native.dll"
    ).exists()

def test_extract_native_rejects_parent_path_traversal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    version = make_version(tmp_path / "version.json")
    native_zip = tmp_path / "native.jar"
    destination = tmp_path / "natives"
    with zipfile.ZipFile(native_zip, "w") as archive:
        archive.writestr("../outside.dll", b"escape")
    monkeypatch.setattr(Paths, "natives", lambda version: destination)

    with pytest.raises(RuntimeError, match="Unsafe path"):
        DownloadLibraryManager._extract_native(native_zip, version, "unsafe")

    assert not (tmp_path / "outside.dll").exists()
    assert not (destination / ".extracted" / "unsafe").exists()


def test_extract_native_rejects_marker_directory_entries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    version = make_version(tmp_path / "version.json")
    native_zip = tmp_path / "native.jar"
    destination = tmp_path / "natives"
    with zipfile.ZipFile(native_zip, "w") as archive:
        archive.writestr(".extracted/fake-marker", b"poison")
    monkeypatch.setattr(Paths, "natives", lambda version: destination)

    with pytest.raises(RuntimeError, match="Unsafe path"):
        DownloadLibraryManager._extract_native(native_zip, version, "real-marker")

    assert not (destination / ".extracted" / "real-marker").exists()
