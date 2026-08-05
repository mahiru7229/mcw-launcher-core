from pathlib import Path
import os
from types import SimpleNamespace

import pytest

from src.core.minecraft.argument_builder import ArgumentBuilder
from src.models.account.account_source import AccountSource
from src.models.instance.settings import InstanceSettings


def make_version(
    *,
    jvm_arguments: list | None = None,
    game_arguments: list | None = None,
):
    return SimpleNamespace(
        arguments={
            "jvm": jvm_arguments or [],
            "game": game_arguments or [],
        }
    )


def make_settings(
    *,
    min_memory: int = 1024,
    max_memory: int = 2048,
    jvm_arguments: list[str] | None = None,
    game_arguments: list[str] | None = None,
    offline_multiplayer_enabled: bool = False,
    width: int = 854,
    height: int = 480,
    fullscreen: bool = False,
) -> InstanceSettings:
    return InstanceSettings(
        java_path=Path("javaw.exe"),
        min_memory=min_memory,
        max_memory=max_memory,
        jvm_arguments=jvm_arguments or [],
        game_arguments=game_arguments or [],
        offline_multiplayer_enabled=offline_multiplayer_enabled,
        width=width,
        height=height,
        fullscreen=fullscreen,
    )


def make_account(
    account_type: AccountSource = AccountSource.OFFLINE
):
    return SimpleNamespace(
        account_type=account_type
    )


def test_build_adds_memory_arguments():
    version = make_version()
    settings = make_settings(
        min_memory=512,
        max_memory=4096,
    )

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert jvm_args[:2] == [
        "-Xms512M",
        "-Xmx4096M",
    ]


def test_build_adds_custom_jvm_arguments_after_memory():
    version = make_version()
    settings = make_settings(
        jvm_arguments=[
            "-XX:+UseG1GC",
            "-Dexample=true",
        ]
    )

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert jvm_args == [
        "-Xms1024M",
        "-Xmx2048M",
        "-XX:+UseG1GC",
        "-Dexample=true",
    ]


def test_build_adds_window_size_arguments():
    version = make_version()
    settings = make_settings(
        width=1280,
        height=720,
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert game_args[:4] == [
        "--width",
        "1280",
        "--height",
        "720",
    ]


def test_build_adds_fullscreen_when_enabled():
    version = make_version()
    settings = make_settings(
        fullscreen=True
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert "--fullscreen" in game_args


def test_build_does_not_add_fullscreen_when_disabled():
    version = make_version()
    settings = make_settings(
        fullscreen=False
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert "--fullscreen" not in game_args


def test_build_adds_custom_game_arguments_after_window_settings():
    version = make_version()
    settings = make_settings(
        game_arguments=[
            "--demo",
            "--quickPlaySingleplayer",
            "Test World",
        ]
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert game_args == [
        "--width",
        "854",
        "--height",
        "480",
        "--demo",
        "--quickPlaySingleplayer",
        "Test World",
    ]


def test_build_resolves_jvm_placeholders():
    version = make_version(
        jvm_arguments=[
            "-Djava.library.path=${natives_directory}",
            "-cp",
            "${classpath}",
        ]
    )
    settings = make_settings()

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={
            "natives_directory": "cache/natives/1.20.1",
            "classpath": "a.jar;b.jar",
        },
        settings=settings,
        account=make_account(),
    )

    assert "-Djava.library.path=cache/natives/1.20.1" in jvm_args
    assert "a.jar;b.jar" in jvm_args


def test_build_resolves_game_placeholders():
    version = make_version(
        game_arguments=[
            "--username",
            "${auth_player_name}",
            "--version",
            "${version_name}",
        ]
    )
    settings = make_settings()

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={
            "auth_player_name": "Steve",
            "version_name": "1.20.1",
        },
        settings=settings,
        account=make_account(),
    )

    assert game_args[-4:] == [
        "--username",
        "Steve",
        "--version",
        "1.20.1",
    ]


def test_build_resolves_forge_module_path_placeholders(tmp_path: Path):
    libraries = tmp_path / "libraries"
    module_a = libraries / "bootstraplauncher.jar"
    module_b = libraries / "securejarhandler.jar"
    version = make_version(
        jvm_arguments=[
            "-p",
            "${library_directory}/bootstraplauncher.jar${classpath_separator}${library_directory}/securejarhandler.jar",
            "--add-modules",
            "ALL-MODULE-PATH",
        ]
    )

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={
            "library_directory": str(libraries),
            "classpath_separator": os.pathsep,
        },
        settings=make_settings(),
        account=make_account(),
    )

    assert jvm_args[-4:] == [
        "-p",
        os.pathsep.join((str(module_a), str(module_b))),
        "--add-modules",
        "ALL-MODULE-PATH",
    ]


def test_build_keeps_unknown_placeholder_unchanged():
    version = make_version(
        game_arguments=[
            "${unknown_value}"
        ]
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=make_settings(),
        account=make_account(),
    )

    assert game_args[-1] == "${unknown_value}"


def test_build_supports_rule_based_jvm_entries():
    version = make_version(
        jvm_arguments=[
            {
                "rules": [
                    {"action": "allow"}
                ],
                "value": "-Dexample=true",
            }
        ]
    )

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=make_settings(),
        account=make_account(),
    )

    assert "-Dexample=true" in jvm_args
    assert all(
        isinstance(argument, str)
        for argument in jvm_args
    )


def test_build_supports_rule_based_game_entries():
    version = make_version(
        game_arguments=[
            {
                "rules": [
                    {"action": "allow"}
                ],
                "value": "--demo",
            }
        ]
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=make_settings(),
        account=make_account(),
    )

    assert "--demo" in game_args
    assert all(
        isinstance(argument, str)
        for argument in game_args
    )


def test_deprecated_offline_multiplayer_setting_does_not_redirect_auth_services():
    version = make_version()
    settings = make_settings(offline_multiplayer_enabled=True)

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(AccountSource.OFFLINE),
    )

    assert not any("nope.invalid" in argument for argument in jvm_args)
    assert not any(
        argument.startswith(prefix)
        for argument in jvm_args
        for prefix in ArgumentBuilder.UNSAFE_OFFLINE_AUTH_HOST_PREFIXES
    )


def test_offline_account_removes_unsafe_custom_auth_host_overrides():
    version = make_version()
    settings = make_settings(
        jvm_arguments=[
            "-Dsafe.option=true",
            "-Dminecraft.api.auth.host=https://nope.invalid",
            "-Dminecraft.api.account.host=https://nope.invalid",
            "-Dminecraft.api.session.host=https://nope.invalid",
            "-Dminecraft.api.services.host=https://nope.invalid",
        ],
    )

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(AccountSource.OFFLINE),
    )

    assert "-Dsafe.option=true" in jvm_args
    assert not any("nope.invalid" in argument for argument in jvm_args)
    assert not any(
        argument.startswith(prefix)
        for argument in jvm_args
        for prefix in ArgumentBuilder.UNSAFE_OFFLINE_AUTH_HOST_PREFIXES
    )


def test_microsoft_account_keeps_explicit_auth_host_overrides():
    override = "-Dminecraft.api.auth.host=https://example.invalid"
    version = make_version()
    settings = make_settings(jvm_arguments=[override])

    jvm_args, _ = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(AccountSource.MICROSOFT),
    )

    assert override in jvm_args


@pytest.mark.parametrize(
    (
        "value",
        "context",
        "expected",
    ),
    [
        (
            "${first}-${second}",
            {
                "first": "alpha",
                "second": "beta",
            },
            "alpha-beta",
        ),
        (
            "${number}",
            {
                "number": 21,
            },
            "21",
        ),
        (
            "plain-value",
            {
                "unused": "value",
            },
            "plain-value",
        ),
        (
            "${same}/${same}",
            {
                "same": "path",
            },
            "path/path",
        ),
    ],
)
def test_resolve_replaces_context_values(
    value: str,
    context: dict,
    expected: str,
):
    assert ArgumentBuilder.resolve(
        value,
        context,
    ) == expected


def test_build_preserves_argument_order():
    version = make_version(
        jvm_arguments=[
            "-Dversion.jvm=1",
            "-Dversion.jvm=2",
        ],
        game_arguments=[
            "--version-game-one",
            "--version-game-two",
        ],
    )
    settings = make_settings(
        jvm_arguments=[
            "-Dsettings.jvm=1",
            "-Dsettings.jvm=2",
        ],
        game_arguments=[
            "--settings-game-one",
            "--settings-game-two",
        ],
        fullscreen=True,
    )

    jvm_args, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=settings,
        account=make_account(),
    )

    assert jvm_args == [
        "-Xms1024M",
        "-Xmx2048M",
        "-Dsettings.jvm=1",
        "-Dsettings.jvm=2",
        "-Dversion.jvm=1",
        "-Dversion.jvm=2",
    ]

    assert game_args == [
        "--width",
        "854",
        "--height",
        "480",
        "--fullscreen",
        "--settings-game-one",
        "--settings-game-two",
        "--version-game-one",
        "--version-game-two",
    ]


def test_build_accepts_version_with_no_arguments():
    version = SimpleNamespace(
        arguments=None
    )

    jvm_args, game_args = ArgumentBuilder.build(
        version=version,
        context={},
        settings=make_settings(),
        account=make_account(),
    )

    assert jvm_args == [
        "-Xms1024M",
        "-Xmx2048M",
    ]
    assert game_args == [
        "--width",
        "854",
        "--height",
        "480",
    ]

def test_build_rejects_rule_based_entry_when_feature_is_disabled():
    version = make_version(
        game_arguments=[
            {
                "rules": [
                    {"action": "allow", "features": {"is_demo_user": True}}
                ],
                "value": "--demo",
            }
        ]
    )

    _, game_args = ArgumentBuilder.build(version=version, context={}, settings=make_settings(), account=make_account())

    assert "--demo" not in game_args


def test_build_accepts_rule_based_entry_when_context_enables_feature():
    version = make_version(
        game_arguments=[
            {
                "rules": [
                    {"action": "allow", "features": {"is_demo_user": True}}
                ],
                "value": "--demo",
            }
        ]
    )

    _, game_args = ArgumentBuilder.build(version=version, context={"argument_features": {"is_demo_user": True}}, settings=make_settings(), account=make_account())

    assert "--demo" in game_args


def test_build_respects_last_matching_argument_rule():
    version = make_version(
        jvm_arguments=[
            {
                "rules": [
                    {"action": "allow"},
                    {"action": "disallow"},
                ],
                "value": "-Dblocked=true",
            }
        ]
    )

    jvm_args, _ = ArgumentBuilder.build(version=version, context={}, settings=make_settings(), account=make_account())

    assert "-Dblocked=true" not in jvm_args


def test_offline_account_normalizes_modern_launch_identity_arguments():
    version = make_version(
        game_arguments=[
            "--username",
            "${auth_player_name}",
            "--uuid",
            "${auth_uuid}",
            "--accessToken",
            "${auth_access_token}",
            "--clientId",
            "${clientid}",
            "--xuid",
            "${auth_xuid}",
            "--userType",
            "${user_type}",
            "--versionType",
            "release",
        ]
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={
            "auth_player_name": "OfflinePlayer",
            "auth_uuid": "5627dd98-e6be-3c21-b8a8-e92344183641",
            "auth_access_token": "stale-token",
            "clientid": "stale-client-id",
            "auth_xuid": "stale-xuid",
            "user_type": "offline",
        },
        settings=make_settings(),
        account=make_account(AccountSource.OFFLINE),
    )

    assert game_args[game_args.index("--username") + 1] == "OfflinePlayer"
    assert game_args[game_args.index("--uuid") + 1] == "5627dd98e6be3c21b8a8e92344183641"
    assert game_args[game_args.index("--accessToken") + 1] == "0"
    assert game_args[game_args.index("--userType") + 1] == "legacy"
    assert "--clientId" not in game_args
    assert "--xuid" not in game_args
    assert "--versionType" in game_args


def test_offline_account_removes_duplicate_or_custom_identity_overrides():
    version = make_version(
        game_arguments=[
            "--username",
            "${auth_player_name}",
            "--uuid",
            "${auth_uuid}",
            "--accessToken",
            "${auth_access_token}",
            "--userType",
            "${user_type}",
        ]
    )
    settings = make_settings(
        game_arguments=[
            "--uuid=invalid",
            "--accessToken",
            "invalid-token",
            "--userType=msa",
            "--clientId=secret",
            "--xuid",
            "secret-xuid",
        ]
    )

    _, game_args = ArgumentBuilder.build(
        version=version,
        context={
            "auth_player_name": "Steve",
            "auth_uuid": "5627dd98e6be3c21b8a8e92344183641",
            "auth_access_token": "0",
            "user_type": "legacy",
        },
        settings=settings,
        account=make_account(AccountSource.OFFLINE),
    )

    assert game_args.count("--uuid") == 1
    assert game_args.count("--accessToken") == 1
    assert game_args.count("--userType") == 1
    assert game_args[game_args.index("--uuid") + 1] == "5627dd98e6be3c21b8a8e92344183641"
    assert game_args[game_args.index("--accessToken") + 1] == "0"
    assert game_args[game_args.index("--userType") + 1] == "legacy"
    assert not any(value.startswith("--clientId") for value in game_args)
    assert not any(value.startswith("--xuid") for value in game_args)


def test_microsoft_account_keeps_modern_identity_arguments_unchanged():
    version = make_version(
        game_arguments=[
            "--uuid",
            "${auth_uuid}",
            "--accessToken",
            "${auth_access_token}",
            "--clientId",
            "${clientid}",
            "--xuid",
            "${auth_xuid}",
            "--userType",
            "${user_type}",
        ]
    )
    context = {
        "auth_uuid": "premium-uuid",
        "auth_access_token": "premium-token",
        "clientid": "premium-client-id",
        "auth_xuid": "premium-xuid",
        "user_type": "msa",
    }

    _, game_args = ArgumentBuilder.build(
        version=version,
        context=context,
        settings=make_settings(),
        account=make_account(AccountSource.MICROSOFT),
    )

    assert game_args[game_args.index("--uuid") + 1] == "premium-uuid"
    assert game_args[game_args.index("--accessToken") + 1] == "premium-token"
    assert game_args[game_args.index("--clientId") + 1] == "premium-client-id"
    assert game_args[game_args.index("--xuid") + 1] == "premium-xuid"
    assert game_args[game_args.index("--userType") + 1] == "msa"


def test_build_removes_user_overrides_for_mcw_lan_agent():
    version = make_version()
    settings = make_settings(
        jvm_arguments=[
            "-Dmcw.lan.offline=false",
            "-Dmcw.lan.target.class=example/Unsafe",
            "-javaagent:C:/cache/mcw-lan-agent.jar",
            "-javaagent:C:/tools/other-agent.jar",
            "-Dexample=true",
        ]
    )

    jvm_args, _ = ArgumentBuilder.build(version=version, context={}, settings=settings, account=make_account())

    assert "-Dmcw.lan.offline=false" not in jvm_args
    assert "-Dmcw.lan.target.class=example/Unsafe" not in jvm_args
    assert "-javaagent:C:/cache/mcw-lan-agent.jar" not in jvm_args
    assert "-javaagent:C:/tools/other-agent.jar" in jvm_args
    assert "-Dexample=true" in jvm_args
