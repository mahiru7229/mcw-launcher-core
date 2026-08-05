import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.core.fs.paths import Paths
from src.core.minecraft.version_manifest_manager import (
    MANIFEST_URL,
    VersionManifestManager,
)
from src.models.minecraft.version_manifest import VersionManifest


def make_manifest_data() -> dict:
    return {
        "latest": {
            "release": "1.21.8",
            "snapshot": "26w28a",
        },
        "versions": [
            {
                "id": "1.21.8",
                "type": "release",
                "url": "https://example.com/1.21.8.json",
                "releaseTime": "2026-07-01T10:30:00+00:00",
            },
            {
                "id": "26w28a",
                "type": "snapshot",
                "url": "https://example.com/26w28a.json",
                "releaseTime": "2026-07-08T12:00:00+00:00",
            },
        ],
    }


def test_download_manifest_writes_response_to_manifest_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = (
        tmp_path
        / "manifest"
        / "version_manifest_v2.json"
    )
    response_text = json.dumps(
        make_manifest_data()
    )

    monkeypatch.setattr(
        Paths,
        "version_manifest",
        lambda: manifest_path,
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout: SimpleNamespace(
            text=response_text
        ),
    )

    result = (
        VersionManifestManager._download_manifest()
    )

    assert result == manifest_path
    assert manifest_path.exists()
    assert manifest_path.read_text(
        encoding="utf-8"
    ) == response_text


def test_download_manifest_creates_parent_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = (
        tmp_path
        / "missing"
        / "nested"
        / "version_manifest_v2.json"
    )

    monkeypatch.setattr(
        Paths,
        "version_manifest",
        lambda: manifest_path,
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout: SimpleNamespace(
            text="{}"
        ),
    )

    assert not manifest_path.parent.exists()

    VersionManifestManager._download_manifest()

    assert manifest_path.parent.exists()


def test_download_manifest_uses_mojang_url_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"
    received = {}

    monkeypatch.setattr(
        Paths,
        "version_manifest",
        lambda: manifest_path,
    )

    def fake_get(url: str, timeout: int):
        received["url"] = url
        received["timeout"] = timeout
        return SimpleNamespace(text="{}")

    monkeypatch.setattr(
        requests,
        "get",
        fake_get,
    )

    VersionManifestManager._download_manifest()

    assert received == {
        "url": MANIFEST_URL,
        "timeout": 10,
    }


def test_download_manifest_returns_none_on_request_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        Paths,
        "version_manifest",
        lambda: tmp_path / "manifest.json",
    )

    def fail_request(*args, **kwargs):
        raise requests.RequestException(
            "network failed"
        )

    monkeypatch.setattr(
        requests,
        "get",
        fail_request,
    )

    result = (
        VersionManifestManager._download_manifest()
    )

    assert result is None


def test_load_manifest_reads_valid_json(
    tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"
    manifest_data = make_manifest_data()

    manifest_path.write_text(
        json.dumps(manifest_data),
        encoding="utf-8",
    )

    result = VersionManifestManager._load_manifest(
        manifest_path
    )

    assert result == manifest_data


def test_load_manifest_returns_empty_dict_for_invalid_json(
    tmp_path: Path,
):
    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    result = VersionManifestManager._load_manifest(
        manifest_path
    )

    assert result == {}


def test_load_manifest_returns_empty_dict_for_none_path():
    assert (
        VersionManifestManager._load_manifest(None)
        == {}
    )


def test_parse_manifest_returns_version_models():
    result = VersionManifestManager._parse_manifest(
        make_manifest_data()
    )

    assert len(result) == 2
    assert all(
        isinstance(item, VersionManifest)
        for item in result
    )

    release = result[0]
    snapshot = result[1]

    assert release.id == "1.21.8"
    assert release.type == "release"
    assert release.url == (
        "https://example.com/1.21.8.json"
    )

    assert snapshot.id == "26w28a"
    assert snapshot.type == "snapshot"
    assert snapshot.url == (
        "https://example.com/26w28a.json"
    )


def test_parse_manifest_converts_release_time_to_datetime():
    result = VersionManifestManager._parse_manifest(
        make_manifest_data()
    )

    assert result[0].release_time == datetime(
        2026,
        7,
        1,
        10,
        30,
        tzinfo=timezone.utc,
    )
    assert result[1].release_time == datetime(
        2026,
        7,
        8,
        12,
        0,
        tzinfo=timezone.utc,
    )


def test_parse_manifest_preserves_version_order():
    data = make_manifest_data()
    data["versions"].reverse()

    result = VersionManifestManager._parse_manifest(
        data
    )

    assert [
        version.id
        for version in result
    ] == [
        "26w28a",
        "1.21.8",
    ]


@pytest.mark.parametrize(
    "invalid_manifest",
    [
        {},
        {"versions": None},
        {"versions": [{}]},
        {
            "versions": [
                {
                    "id": "1.20.1",
                    "type": "release",
                    "url": "https://example.com/version.json",
                }
            ]
        },
        {
            "versions": [
                {
                    "id": "1.20.1",
                    "type": "release",
                    "url": "https://example.com/version.json",
                    "releaseTime": "not-a-date",
                }
            ]
        },
    ],
)
def test_parse_manifest_returns_empty_list_for_invalid_data(
    invalid_manifest: dict,
):
    result = VersionManifestManager._parse_manifest(
        invalid_manifest
    )

    assert result == []


def test_get_orchestrates_download_load_and_parse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"
    manifest_data = make_manifest_data()
    parsed_result = [object()]
    calls = []

    def fake_download():
        calls.append(("download",))
        return manifest_path

    def fake_load(received_path):
        calls.append(("load", received_path))
        return manifest_data

    def fake_parse(received_manifest):
        calls.append(
            ("parse", received_manifest)
        )
        return parsed_result

    monkeypatch.setattr(
        VersionManifestManager,
        "_download_manifest",
        fake_download,
    )
    monkeypatch.setattr(
        VersionManifestManager,
        "_load_manifest",
        fake_load,
    )
    monkeypatch.setattr(
        VersionManifestManager,
        "_parse_manifest",
        fake_parse,
    )

    result = VersionManifestManager.get()

    assert result is parsed_result
    assert calls == [
        ("download",),
        ("load", manifest_path),
        ("parse", manifest_data),
    ]


def test_latest_version_returns_latest_release(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"

    monkeypatch.setattr(
        VersionManifestManager,
        "_download_manifest",
        lambda: manifest_path,
    )
    monkeypatch.setattr(
        VersionManifestManager,
        "_load_manifest",
        lambda path: make_manifest_data(),
    )

    result = VersionManifestManager.latest_version()

    assert result == "1.21.8"


def test_latest_version_returns_latest_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"

    monkeypatch.setattr(
        VersionManifestManager,
        "_download_manifest",
        lambda: manifest_path,
    )
    monkeypatch.setattr(
        VersionManifestManager,
        "_load_manifest",
        lambda path: make_manifest_data(),
    )

    result = VersionManifestManager.latest_version(
        is_snapshot=True
    )

    assert result == "26w28a"


@pytest.mark.parametrize(
    "manifest_data",
    [
        {},
        {"latest": {}},
        {"latest": None},
    ],
)
def test_latest_version_returns_empty_string_for_invalid_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    manifest_data: dict,
):
    monkeypatch.setattr(
        VersionManifestManager,
        "_download_manifest",
        lambda: tmp_path / "manifest.json",
    )
    monkeypatch.setattr(
        VersionManifestManager,
        "_load_manifest",
        lambda path: manifest_data,
    )

    assert (
        VersionManifestManager.latest_version()
        == ""
    )


def test_latest_version_returns_empty_string_after_download_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        VersionManifestManager,
        "_download_manifest",
        lambda: None,
    )

    assert (
        VersionManifestManager.latest_version()
        == ""
    )

def test_download_manifest_uses_cached_file_after_network_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    cached = make_manifest_data()
    manifest_path.write_text(json.dumps(cached), encoding="utf-8")
    monkeypatch.setattr(Paths, "version_manifest", lambda: manifest_path)

    def fail_request(*args, **kwargs):
        raise requests.RequestException("offline")

    monkeypatch.setattr(requests, "get", fail_request)

    assert VersionManifestManager._download_manifest() == manifest_path
    assert VersionManifestManager.get()[0].id == "1.21.8"


def test_download_manifest_does_not_replace_cache_with_invalid_response(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    cached_text = json.dumps(make_manifest_data())
    manifest_path.write_text(cached_text, encoding="utf-8")
    monkeypatch.setattr(Paths, "version_manifest", lambda: manifest_path)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: SimpleNamespace(text="<html>error</html>"))

    assert VersionManifestManager._download_manifest() == manifest_path
    assert manifest_path.read_text(encoding="utf-8") == cached_text
