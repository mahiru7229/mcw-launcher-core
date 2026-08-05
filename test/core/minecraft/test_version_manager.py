import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.core.fs.paths import Paths
from src.core.minecraft.version_manager import VersionManager
from src.core.minecraft.version_manifest_manager import VersionManifestManager
from src.models.minecraft.version import Version


def make_manifest(
    version_id: str,
    url: str = "https://example.com/version.json",
):
    return SimpleNamespace(
        id=version_id,
        url=url,
    )


def make_version_data(
    *,
    version_id: str = "1.20.1",
    version_type: str = "release",
) -> dict:
    return {
        "id": version_id,
        "arguments": {
            "game": [],
            "jvm": [],
        },
        "libraries": [],
        "downloads": {
            "client": {
                "url": "https://example.com/client.jar",
                "sha1": "abc",
            }
        },
        "assetIndex": {
            "id": "5",
            "url": "https://example.com/assets.json",
        },
        "assets": "5",
        "mainClass": "net.minecraft.client.main.Main",
        "javaVersion": {
            "majorVersion": 17,
        },
        "type": version_type,
    }


def test_parse_version_returns_version_model(
    tmp_path: Path,
):
    version_path = tmp_path / "1.20.1.json"
    version_data = make_version_data()

    version = VersionManager._parse_version(
        version_data,
        version_path,
    )

    assert isinstance(version, Version)
    assert version.id == "1.20.1"
    assert version.path == version_path
    assert version.arguments == version_data["arguments"]
    assert version.libraries == []
    assert version.downloads == version_data["downloads"]
    assert version.asset_index == version_data["assetIndex"]
    assert version.assets == "5"
    assert version.main_class == (
        "net.minecraft.client.main.Main"
    )
    assert version.java_version == {
        "majorVersion": 17
    }
    assert version.raw_json is version_data
    assert version.type == "release"


def test_parse_version_preserves_explicit_type(
    tmp_path: Path,
):
    version_data = make_version_data(
        version_type="snapshot"
    )

    version = VersionManager._parse_version(
        version_data,
        tmp_path / "snapshot.json",
    )

    assert version is not None
    assert version.type == "snapshot"


def test_parse_version_defaults_type_to_release(
    tmp_path: Path,
):
    version_data = make_version_data()
    version_data.pop("type")

    version = VersionManager._parse_version(
        version_data,
        tmp_path / "version.json",
    )

    assert version is not None
    assert version.type == "release"


@pytest.mark.parametrize(
    "missing_key",
        [
        "id",
        "libraries",
        "downloads",
        "assetIndex",
        "assets",
        "mainClass",
    ],
)
def test_parse_version_returns_none_when_required_field_is_missing(
    tmp_path: Path,
    missing_key: str,
):
    version_data = make_version_data()
    version_data.pop(missing_key)

    version = VersionManager._parse_version(
        version_data,
        tmp_path / "invalid.json",
    )

    assert version is None


def test_load_version_reads_json_file(
    tmp_path: Path,
):
    version_path = tmp_path / "version.json"
    expected = make_version_data()

    version_path.write_text(
        json.dumps(expected),
        encoding="utf-8",
    )

    result = VersionManager._load_version(
        version_path
    )

    assert result == expected


def test_load_version_returns_empty_dict_for_invalid_json(
    tmp_path: Path,
):
    version_path = tmp_path / "invalid.json"
    version_path.write_text(
        "{invalid-json",
        encoding="utf-8",
    )

    result = VersionManager._load_version(
        version_path
    )

    assert result == {}


def test_choosing_version_returns_matching_manifest(
    monkeypatch: pytest.MonkeyPatch,
):
    versions = [
        make_manifest("1.19.4"),
        make_manifest("1.20.1"),
        make_manifest("1.21.1"),
    ]

    monkeypatch.setattr(
        VersionManifestManager,
        "get",
        lambda: versions,
    )

    selected = VersionManager._choosing_version(
        "1.20.1"
    )

    assert selected is versions[1]


def test_choosing_version_raises_when_id_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        VersionManifestManager,
        "get",
        lambda: [
            make_manifest("1.20.1"),
            make_manifest("1.21.1"),
        ],
    )

    with pytest.raises(RuntimeError):
        VersionManager._choosing_version(
            "missing-version"
        )


def test_download_version_writes_response_to_expected_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest = make_manifest("1.20.1")
    version_path = tmp_path / "versions" / "1.20.1.json"

    response = SimpleNamespace(
        text=json.dumps(make_version_data())
    )

    monkeypatch.setattr(
        Paths,
        "version_json",
        lambda version: version_path,
    )
    monkeypatch.setattr(
        requests,
        "get",
        lambda url, timeout: response,
    )

    result = VersionManager._download_version(
        manifest
    )

    assert result == version_path
    assert version_path.exists()
    assert json.loads(
        version_path.read_text(encoding="utf-8")
    ) == make_version_data()


def test_download_version_uses_manifest_url_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest = make_manifest(
        "1.20.1",
        "https://example.com/1.20.1.json",
    )
    received = {}

    monkeypatch.setattr(
        Paths,
        "version_json",
        lambda version: tmp_path / "version.json",
    )

    def fake_get(url: str, timeout: int):
        received["url"] = url
        received["timeout"] = timeout
        return SimpleNamespace(
            text="{}"
        )

    monkeypatch.setattr(
        requests,
        "get",
        fake_get,
    )

    VersionManager._download_version(
        manifest
    )

    assert received == {
        "url": "https://example.com/1.20.1.json",
        "timeout": 10,
    }


def test_download_version_returns_none_on_request_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest = make_manifest("1.20.1")

    monkeypatch.setattr(
        Paths,
        "version_json",
        lambda version: tmp_path / "version.json",
    )

    def fail_get(*args, **kwargs):
        raise requests.RequestException(
            "network failed"
        )

    monkeypatch.setattr(
        requests,
        "get",
        fail_get,
    )

    result = VersionManager._download_version(
        manifest
    )

    assert result is None


def test_load_orchestrates_choose_download_load_and_parse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    manifest = make_manifest("1.20.1")
    version_path = tmp_path / "1.20.1.json"
    version_data = make_version_data()
    parsed_version = object()

    calls = []

    def fake_choose(version_id: str):
        calls.append(
            ("choose", version_id)
        )
        return manifest

    def fake_download(received_manifest):
        calls.append(
            ("download", received_manifest)
        )
        return version_path

    def fake_load(received_path):
        calls.append(
            ("load", received_path)
        )
        return version_data

    def fake_parse(received_data, received_path):
        calls.append(
            ("parse", received_data, received_path)
        )
        return parsed_version

    monkeypatch.setattr(
        VersionManager,
        "_choosing_version",
        fake_choose,
    )
    monkeypatch.setattr(
        VersionManager,
        "_download_version",
        fake_download,
    )
    monkeypatch.setattr(
        VersionManager,
        "_load_version",
        fake_load,
    )
    monkeypatch.setattr(
        VersionManager,
        "_parse_version",
        fake_parse,
    )

    result = VersionManager.load(
        "1.20.1"
    )

    assert result is parsed_version
    assert calls == [
        ("choose", "1.20.1"),
        ("download", manifest),
        ("load", version_path),
        ("parse", version_data, version_path),
    ]


def test_load_raises_clean_runtime_error_when_download_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        VersionManager,
        "_choosing_version",
        lambda version_id: make_manifest(version_id),
    )
    monkeypatch.setattr(
        VersionManager,
        "_download_version",
        lambda manifest: None,
    )

    with pytest.raises(
        RuntimeError,
        match="Cannot download version metadata",
    ):
        VersionManager.load(
            "1.20.1"
        )