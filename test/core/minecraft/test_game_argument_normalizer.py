from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.fs.paths import Paths
from src.core.minecraft.classpath_builder import ClasspathBuilder
from src.core.minecraft.game_argument_normalizer import GameArgumentNormalizer
from src.core.minecraft.launcher_manager import LauncherManager
from src.models.account.account_source import AccountSource
from src.models.instance.settings import InstanceSettings


def test_normalize_keeps_only_one_canonical_game_directory() -> None:
    arguments = [
        "--username",
        "Steve",
        "--gameDir",
        "D:/custom-instance",
        "--gameDir=C:/inherited-instance",
        "--assetsDir",
        "C:/assets",
    ]

    normalized = GameArgumentNormalizer.normalize(
        arguments,
        {"game_directory": "C:/MCW/instances/Forge 1.12.2"},
    )

    assert normalized.count("--gameDir") == 1
    assert not any(value.startswith("--gameDir=") for value in normalized)
    index = normalized.index("--gameDir")
    assert normalized[index + 1] == "C:/MCW/instances/Forge 1.12.2"
    assert normalized[:2] == ["--username", "Steve"]


def test_normalize_uses_last_value_for_non_context_singletons() -> None:
    normalized = GameArgumentNormalizer.normalize(
        ["--width", "854", "--width=1280", "--height", "720"],
        {},
    )

    assert normalized == ["--width", "1280", "--height", "720"]


def test_normalize_rejects_single_value_option_without_a_value() -> None:
    with pytest.raises(RuntimeError, match=r"--gameDir requires exactly one non-empty value"):
        GameArgumentNormalizer.normalize(["--gameDir"], {})


def test_launcher_build_normalizes_inherited_forge_legacy_game_dir_and_custom_conflict(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    version = SimpleNamespace(
        id="forge-1.12.2-14.23.5.2860",
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={
            "inheritsFrom": "1.12.2",
            "forge": {"loaderVersion": "14.23.5.2860"},
        },
        arguments=None,
        minecraft_arguments=(
            "--username ${auth_player_name} "
            "--version ${version_name} "
            "--gameDir ${game_directory} "
            "--assetsDir ${assets_root} "
            "--assetIndex ${assets_index_name} "
            "--uuid ${auth_uuid} "
            "--accessToken ${auth_access_token} "
            "--userType ${user_type} "
            "--versionType ${version_type} "
            "--gameDir D:/forge-profile-duplicate "
            "--tweakClass net.minecraftforge.fml.common.launcher.FMLTweaker"
        ),
    )
    settings = InstanceSettings(
        java_path=Path("javaw.exe"),
        min_memory=1024,
        max_memory=4096,
        jvm_arguments=[],
        game_arguments=["--gameDir=D:/custom-override"],
        offline_multiplayer_enabled=False,
        width=1280,
        height=720,
        fullscreen=False,
    )
    account = SimpleNamespace(account_type=AccountSource.MICROSOFT)
    context = {
        "auth_player_name": "Steve",
        "version_name": version.id,
        "game_directory": str(tmp_path / "instances" / "Forge 1.12.2"),
        "assets_root": str(tmp_path / "assets"),
        "assets_index_name": "1.12",
        "auth_uuid": "premium-uuid",
        "auth_access_token": "premium-token",
        "user_type": "msa",
        "version_type": "release",
        "natives_directory": str(tmp_path / "natives"),
        "launcher_name": "mcw-launcher",
        "launcher_version": "1.1.0-beta.5",
    }

    monkeypatch.setattr(Paths, "client", lambda _version: tmp_path / "1.12.2.jar")
    monkeypatch.setattr(Paths, "libraries", lambda: tmp_path / "libraries")
    monkeypatch.setattr(ClasspathBuilder, "build", lambda *_args: "legacy-classpath")

    command = LauncherManager.build(version, context, settings, account)
    main_index = command.index("net.minecraft.launchwrapper.Launch")
    game_arguments = command[main_index + 1 :]

    assert game_arguments.count("--gameDir") == 1
    assert not any(value.startswith("--gameDir=") for value in game_arguments)
    game_dir_index = game_arguments.index("--gameDir")
    assert game_arguments[game_dir_index + 1] == context["game_directory"]
    assert game_arguments.count("--tweakClass") == 1


def test_launcher_build_validates_reserved_single_value_arguments_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    version = SimpleNamespace(
        id="forge-1.12.2",
        main_class="net.minecraft.launchwrapper.Launch",
        raw_json={},
    )
    settings = SimpleNamespace(offline_multiplayer_enabled=False)
    account = SimpleNamespace(account_type=AccountSource.MICROSOFT)

    monkeypatch.setattr(Paths, "client", lambda _version: tmp_path / "client.jar")
    monkeypatch.setattr(Paths, "libraries", lambda: tmp_path / "libraries")
    monkeypatch.setattr(ClasspathBuilder, "build", lambda *_args: "legacy-classpath")
    monkeypatch.setattr(
        "src.core.minecraft.launcher_manager.ArgumentBuilder.build",
        lambda *_args: ([], ["--gameDir"]),
    )

    with pytest.raises(RuntimeError, match=r"--gameDir requires exactly one non-empty value"):
        LauncherManager.build(version, {}, settings, account)
