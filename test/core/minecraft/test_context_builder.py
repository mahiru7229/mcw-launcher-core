from pathlib import Path
import os
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.classpath_builder import ClasspathBuilder
from src.core.minecraft.context_builder import ContextBuilder


@pytest.fixture
def version():
    return SimpleNamespace(
        id="1.20.1",
        assets="5",
        raw_json={
            "type": "release"
        },
    )


@pytest.fixture
def instance():
    return SimpleNamespace(
        name="Test Instance",
        instance_dir=Path("custom") / "Test Instance",
    )


@pytest.fixture
def player_data():
    return SimpleNamespace(
        player_name="Steve",
        uuid="00000000-0000-0000-0000-000000000000",
        access_token="offline-access-token",
        xuid="offline-xuid",
        client_id="mcw-client-id",
    )


@pytest.fixture
def mocked_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    client_path = tmp_path / "cache" / "versions" / "1.20.1" / "1.20.1.jar"
    libraries_path = tmp_path / "cache" / "libraries"
    natives_path = tmp_path / "cache" / "natives" / "1.20.1"
    instance_path = tmp_path / "instances" / "Test Instance"
    assets_path = tmp_path / "cache" / "assets"

    monkeypatch.setattr(
        Paths,
        "client",
        lambda version: client_path,
    )
    monkeypatch.setattr(
        Paths,
        "libraries",
        lambda: libraries_path,
    )
    monkeypatch.setattr(
        Paths,
        "natives",
        lambda version: natives_path,
    )
    monkeypatch.setattr(
        Paths,
        "load_instance_dir",
        lambda name: instance_path,
    )
    monkeypatch.setattr(
        Paths,
        "assets_dir",
        lambda: assets_path,
    )

    return {
        "client": client_path,
        "libraries": libraries_path,
        "natives": natives_path,
        "instance": instance_path,
        "assets": assets_path,
    }


def test_build_calls_classpath_builder_with_expected_paths(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    received = {}

    def fake_build(
        received_version,
        client_path,
        libraries_path,
    ):
        received["version"] = received_version
        received["client"] = client_path
        received["libraries"] = libraries_path
        return "library.jar;client.jar"

    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        fake_build,
    )

    ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert received == {
        "version": version,
        "client": mocked_paths["client"],
        "libraries": mocked_paths["libraries"],
    }


def test_build_uses_classpath_builder_result(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "first.jar;second.jar;client.jar",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["classpath"] == (
        "first.jar;second.jar;client.jar"
    )


def test_build_contains_launcher_information(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["launcher_name"] == "mcw-launcher"
    assert context["launcher_version"] == "1.0"


def test_build_contains_minecraft_paths_as_strings(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["natives_directory"] == str(
        mocked_paths["natives"]
    )
    assert context["game_directory"] == str(
        mocked_paths["instance"]
    )
    assert context["assets_root"] == str(
        mocked_paths["assets"]
    )
    assert context["library_directory"] == str(
        mocked_paths["libraries"]
    )
    assert context["classpath_separator"] == os.pathsep

    assert isinstance(
        context["natives_directory"],
        str,
    )
    assert isinstance(
        context["game_directory"],
        str,
    )
    assert isinstance(
        context["assets_root"],
        str,
    )


def test_build_contains_version_information(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["assets_index_name"] == "5"
    assert context["version_name"] == "1.20.1"
    assert context["version_type"] == "release"


def test_build_uses_release_when_version_type_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    player_data,
    mocked_paths,
):
    version = SimpleNamespace(
        id="1.20.1",
        assets="5",
        raw_json={},
    )

    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["version_type"] == "release"


@pytest.mark.parametrize(
    ("version_type", "expected"),
    [
        ("snapshot", "snapshot"),
        ("old_alpha", "old_alpha"),
        ("old_beta", "old_beta"),
        ("custom", "custom"),
    ],
)
def test_build_preserves_explicit_version_type(
    monkeypatch: pytest.MonkeyPatch,
    instance,
    player_data,
    mocked_paths,
    version_type: str,
    expected: str,
):
    version = SimpleNamespace(
        id="custom-version",
        assets="legacy",
        raw_json={
            "type": version_type
        },
    )

    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["version_type"] == expected


def test_build_contains_authentication_information(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["auth_player_name"] == "Steve"
    assert context["auth_uuid"] == (
        "00000000-0000-0000-0000-000000000000"
    )
    assert context["auth_access_token"] == (
        "offline-access-token"
    )
    assert context["auth_xuid"] == "offline-xuid"
    assert context["clientid"] == "mcw-client-id"


def test_build_keeps_none_authentication_values(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    mocked_paths,
):
    player_data = SimpleNamespace(
        player_name="OfflinePlayer",
        uuid="offline-uuid",
        access_token=None,
        xuid=None,
        client_id=None,
    )

    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert context["auth_player_name"] == "OfflinePlayer"
    assert context["auth_uuid"] == "offline-uuid"
    assert context["auth_access_token"] is None
    assert context["auth_xuid"] is None
    assert context["clientid"] is None


def test_build_returns_exact_public_context_keys(
    monkeypatch: pytest.MonkeyPatch,
    version,
    instance,
    player_data,
    mocked_paths,
):
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "classpath",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert set(context) == {
        "classpath",
        "library_directory",
        "classpath_separator",
        "natives_directory",
        "launcher_name",
        "launcher_version",
        "game_directory",
        "assets_root",
        "assets_index_name",
        "version_name",
        "auth_player_name",
        "auth_uuid",
        "auth_access_token",
        "user_properties",
        "auth_xuid",
        "clientid",
        "version_type",
        "user_type",
    }


def test_build_uses_instance_name_to_resolve_game_directory(
    monkeypatch: pytest.MonkeyPatch,
    version,
    player_data,
    mocked_paths,
):
    instance = SimpleNamespace(
        name="Resolved By Name",
        instance_dir=Path("ignored-custom-directory"),
    )

    received_names = []

    def fake_load_instance_dir(name: str):
        received_names.append(name)
        return Path("instances") / name

    monkeypatch.setattr(
        Paths,
        "load_instance_dir",
        fake_load_instance_dir,
    )
    monkeypatch.setattr(
        ClasspathBuilder,
        "build",
        lambda *_: "",
    )

    context = ContextBuilder.build(
        instance=instance,
        version=version,
        player_data=player_data,
    )

    assert received_names == ["Resolved By Name"]
    assert context["game_directory"] == str(
        Path("instances") / "Resolved By Name"
    )