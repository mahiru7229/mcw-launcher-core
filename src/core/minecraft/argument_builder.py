from src.models.minecraft.version import Version
from src.models.instance.settings import InstanceSettings
from src.models.account.account_source import AccountSource
from src.models.account.account import Account
from src.core.minecraft.library_rule_manager import LibraryRuleManager
from src.core.lan.lan_agent_manager import LanAgentManager
import os
import shlex


class ArgumentBuilder:
    # MCW Launcher previously redirected Mojang service hosts to ``nope.invalid``
    # when the legacy offline multiplayer option was enabled. Offline accounts
    # do not need this redirect to launch or join offline-mode servers, and Forge
    # interprets it as an authentication outage. Keep the persisted setting for
    # backwards compatibility, but never emit or retain those JVM properties.
    UNSAFE_OFFLINE_AUTH_HOST_PREFIXES = (
        "-Dminecraft.api.auth.host=",
        "-Dminecraft.api.account.host=",
        "-Dminecraft.api.session.host=",
        "-Dminecraft.api.services.host=",
    )
    OFFLINE_IDENTITY_ARGUMENTS = (
        "--username",
        "--uuid",
        "--accessToken",
        "--userType",
        "--clientId",
        "--xuid",
    )
    OFFLINE_OMITTED_ARGUMENTS = {"--clientId", "--xuid"}
    DEFAULT_ARGUMENT_FEATURES = {
        "is_demo_user": False,
        "has_custom_resolution": False,
        "has_quick_plays_support": False,
        "is_quick_play_singleplayer": False,
        "is_quick_play_multiplayer": False,
        "is_quick_play_realms": False,
    }

    @staticmethod
    def build(version: Version, context: dict, settings: InstanceSettings, account: Account) -> tuple[list[str], list[str]]:
        user_jvm_arguments = LanAgentManager.sanitize_user_jvm_arguments(settings.jvm_arguments)
        jvm_args: list[str] = [f"-Xms{settings.min_memory}M", f"-Xmx{settings.max_memory}M", *user_jvm_arguments]
        game_args: list[str] = ["--width", str(settings.width), "--height", str(settings.height)]

        if settings.fullscreen:
            game_args.append("--fullscreen")
        game_args += settings.game_arguments

        arguments = getattr(version, "arguments", None) or {}
        minecraft_arguments = getattr(version, "minecraft_arguments", None)

        for argument in arguments.get("jvm", []):
            jvm_args.extend(ArgumentBuilder._resolve_argument_entry(argument, context))

        modern_game_arguments = arguments.get("game", [])
        if modern_game_arguments:
            for argument in modern_game_arguments:
                game_args.extend(ArgumentBuilder._resolve_argument_entry(argument, context))
        elif minecraft_arguments:
            for argument in shlex.split(minecraft_arguments, posix=False):
                game_args.append(ArgumentBuilder.resolve(argument, context))

        if minecraft_arguments:
            legacy_jvm_args = [
                f"-Djava.library.path={context['natives_directory']}",
                f"-Dminecraft.launcher.brand={context['launcher_name']}",
                f"-Dminecraft.launcher.version={context['launcher_version']}",
            ]
            for argument in legacy_jvm_args:
                if argument not in jvm_args:
                    jvm_args.append(argument)

        if account.account_type == AccountSource.OFFLINE:
            jvm_args = ArgumentBuilder._remove_unsafe_offline_auth_overrides(jvm_args)
            game_args = ArgumentBuilder._normalize_offline_identity_arguments(game_args, context)

        return jvm_args, game_args

    @staticmethod
    def _remove_unsafe_offline_auth_overrides(arguments: list[str]) -> list[str]:
        return [
            argument
            for argument in arguments
            if not any(argument.startswith(prefix) for prefix in ArgumentBuilder.UNSAFE_OFFLINE_AUTH_HOST_PREFIXES)
        ]

    @staticmethod
    def _normalize_offline_identity_arguments(arguments: list[str], context: dict) -> list[str]:
        canonical_values = {
            "--username": str(context.get("auth_player_name") or "").strip(),
            "--uuid": str(context.get("auth_uuid") or "").replace("-", "").strip(),
            "--accessToken": "0",
            "--userType": "legacy",
        }

        normalized: list[str] = []
        seen: set[str] = set()
        index = 0

        while index < len(arguments):
            argument = str(arguments[index])
            matched_flag = next((flag for flag in ArgumentBuilder.OFFLINE_IDENTITY_ARGUMENTS if argument == flag or argument.startswith(flag + "=")), None)
            if matched_flag is None:
                normalized.append(argument)
                index += 1
                continue

            inline_value = argument.startswith(matched_flag + "=")
            index += 1 if inline_value else 2

            if matched_flag in seen or matched_flag in ArgumentBuilder.OFFLINE_OMITTED_ARGUMENTS:
                continue

            value = canonical_values.get(matched_flag, "")
            if not value:
                continue

            normalized.extend((matched_flag, value))
            seen.add(matched_flag)

        return normalized

    @staticmethod
    def _resolve_argument_entry(argument: object, context: dict) -> list[str]:
        if isinstance(argument, str):
            return [ArgumentBuilder.resolve(argument, context)]
        if not isinstance(argument, dict):
            return []

        rules = argument.get("rules")
        if rules and not ArgumentBuilder._are_rules_allowed(rules, context):
            return []

        value = argument.get("value", [])
        values = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        return [ArgumentBuilder.resolve(item, context) for item in values if isinstance(item, str)]

    @staticmethod
    def _are_rules_allowed(rules: object, context: dict) -> bool:
        if not isinstance(rules, list):
            return True

        features = dict(ArgumentBuilder.DEFAULT_ARGUMENT_FEATURES)
        context_features = context.get("argument_features", {})
        if isinstance(context_features, dict):
            features.update({str(key): bool(value) for key, value in context_features.items()})

        allowed = False
        for rule in rules:
            if not isinstance(rule, dict) or not LibraryRuleManager._is_rule_matching(rule):
                continue
            required_features = rule.get("features", {})
            if isinstance(required_features, dict) and any(features.get(str(name), False) != bool(expected) for name, expected in required_features.items()):
                continue
            allowed = rule.get("action") == "allow"

        return allowed

    @staticmethod
    def resolve(value: str, context: dict) -> str:
        value = ArgumentBuilder._resolve_library_directory(value, context)
        for key, replacement in context.items():
            if key == "library_directory":
                continue
            value = value.replace("${" + key + "}", str(replacement))
        return value

    @staticmethod
    def _resolve_library_directory(value: str, context: dict) -> str:
        token = "${library_directory}"
        if token not in value or "library_directory" not in context:
            return value

        library_directory = os.path.normpath(str(context["library_directory"]))
        value = value.replace(token + "/", library_directory + os.sep)
        value = value.replace(token + "\\", library_directory + os.sep)
        return value.replace(token, library_directory)
