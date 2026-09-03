import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.minecraft.classpath_builder import ClasspathBuilder
from src.core.minecraft.library_rule_manager import LibraryRuleManager


def make_version(libraries: list[dict]):
    return SimpleNamespace(
        libraries=libraries
    )


def make_library(
    artifact_path: str,
    *,
    rules: list[dict] | None = None,
) -> dict:
    library = {
        "downloads": {
            "artifact": {
                "path": artifact_path
            }
        }
    }

    if rules is not None:
        library["rules"] = rules

    return library


def test_build_returns_client_only_when_no_libraries(
    tmp_path: Path,
):
    client_path = tmp_path / "versions" / "1.20.1.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result == str(client_path)


def test_build_adds_allowed_library_before_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([
        make_library(
            "com/example/example/1.0/example-1.0.jar"
        )
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    expected_library = (
        libraries_dir
        / "com/example/example/1.0/example-1.0.jar"
    )

    assert result == os.pathsep.join([
        str(expected_library),
        str(client_path),
    ])


def test_build_uses_platform_path_separator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([
        make_library("first.jar"),
        make_library("second.jar"),
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep) == [
        str(libraries_dir / "first.jar"),
        str(libraries_dir / "second.jar"),
        str(client_path),
    ]


def test_build_preserves_library_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([
        make_library("third/library.jar"),
        make_library("first/library.jar"),
        make_library("second/library.jar"),
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep) == [
        str(libraries_dir / "third/library.jar"),
        str(libraries_dir / "first/library.jar"),
        str(libraries_dir / "second/library.jar"),
        str(client_path),
    ]


@pytest.mark.parametrize("unsafe_path", ["../escape.jar", "/absolute.jar", "C:/escape.jar", "a//b.jar"])
def test_build_rejects_unsafe_library_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    unsafe_path: str,
):
    monkeypatch.setattr(LibraryRuleManager, "is_allowed", lambda _library: True)

    with pytest.raises(RuntimeError, match="Unsafe library classpath"):
        ClasspathBuilder.build(
            version=make_version([make_library(unsafe_path)]),
            client_path=tmp_path / "client.jar",
            libraries_dir=tmp_path / "libraries",
        )


def test_build_skips_library_rejected_by_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    allowed_library = make_library("allowed.jar")
    blocked_library = make_library("blocked.jar")

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: library is allowed_library,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([
        allowed_library,
        blocked_library,
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep) == [
        str(libraries_dir / "allowed.jar"),
        str(client_path),
    ]


def test_build_calls_rule_manager_for_every_library(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    libraries = [
        make_library("one.jar"),
        make_library("two.jar"),
        make_library("three.jar"),
    ]
    received = []

    def fake_is_allowed(library: dict) -> bool:
        received.append(library)
        return True

    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        fake_is_allowed,
    )

    ClasspathBuilder.build(
        version=make_version(libraries),
        client_path=tmp_path / "client.jar",
        libraries_dir=tmp_path / "libraries",
    )

    assert received == libraries


def test_build_skips_library_without_downloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    version = make_version([
        {
            "name": "legacy:library:1.0"
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=tmp_path / "libraries",
    )

    assert result == str(client_path)


def test_build_adds_existing_legacy_maven_library_without_download_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    libraries_dir = tmp_path / "libraries"
    launchwrapper = libraries_dir / "net/minecraft/launchwrapper/1.8/launchwrapper-1.8.jar"
    launchwrapper.parent.mkdir(parents=True)
    launchwrapper.write_bytes(b"launchwrapper")
    client_path = tmp_path / "client.jar"
    version = make_version([
        {
            "name": "net.minecraft:launchwrapper:1.8"
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep) == [
        str(launchwrapper),
        str(client_path),
    ]


def test_build_skips_library_with_none_downloads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    version = make_version([
        {
            "downloads": None
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=tmp_path / "libraries",
    )

    assert result == str(client_path)


def test_build_skips_library_without_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    version = make_version([
        {
            "downloads": {
                "classifiers": {
                    "natives-windows": {
                        "path": "native.jar"
                    }
                }
            }
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=tmp_path / "libraries",
    )

    assert result == str(client_path)


def test_build_skips_library_with_none_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    version = make_version([
        {
            "downloads": {
                "artifact": None
            }
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=tmp_path / "libraries",
    )

    assert result == str(client_path)


def test_build_does_not_add_native_classifier_to_classpath(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    version = make_version([
        {
            "downloads": {
                "artifact": {
                    "path": "normal/library.jar"
                },
                "classifiers": {
                    "natives-windows": {
                        "path": "native/library-natives-windows.jar"
                    }
                }
            }
        }
    ])

    result = ClasspathBuilder.build(
        version=version,
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    entries = result.split(os.pathsep)

    assert str(
        libraries_dir / "normal/library.jar"
    ) in entries
    assert str(
        libraries_dir
        / "native/library-natives-windows.jar"
    ) not in entries


def test_build_accepts_windows_style_artifact_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    artifact_path = "com\\example\\library.jar"

    result = ClasspathBuilder.build(
        version=make_version([
            make_library(artifact_path)
        ]),
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep)[0] == str(
        libraries_dir / Path("com/example/library.jar")
    )


def test_build_keeps_duplicate_library_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """
    Documents the current behavior.

    ClasspathBuilder currently does not remove duplicate paths.
    """
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    client_path = tmp_path / "client.jar"
    libraries_dir = tmp_path / "libraries"
    duplicate = make_library("duplicate.jar")

    result = ClasspathBuilder.build(
        version=make_version([
            duplicate,
            duplicate,
        ]),
        client_path=client_path,
        libraries_dir=libraries_dir,
    )

    assert result.split(os.pathsep) == [
        str(libraries_dir / "duplicate.jar"),
        str(libraries_dir / "duplicate.jar"),
        str(client_path),
    ]


def test_build_returns_string_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "is_allowed",
        lambda library: True,
    )

    result = ClasspathBuilder.build(
        version=make_version([
            make_library("library.jar")
        ]),
        client_path=tmp_path / "client.jar",
        libraries_dir=tmp_path / "libraries",
    )

    assert isinstance(result, str)
    assert all(
        isinstance(entry, str)
        for entry in result.split(os.pathsep)
    )
