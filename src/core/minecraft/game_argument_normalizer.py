from __future__ import annotations


class GameArgumentNormalizer:
    """Normalize game arguments before Java starts Minecraft.

    Legacy Forge profiles can merge the inherited Minecraft ``minecraftArguments``
    string with another complete Forge argument string. That can leave singleton
    jopt-simple options such as ``--gameDir`` in the command more than once. The
    LaunchWrapper parser rejects those duplicates before Minecraft can start.
    """

    SINGLE_VALUE_OPTIONS = frozenset(
        {
            "--accessToken",
            "--assetIndex",
            "--assetsDir",
            "--clientId",
            "--gameDir",
            "--height",
            "--launchTarget",
            "--quickPlayMultiplayer",
            "--quickPlayPath",
            "--quickPlayRealms",
            "--quickPlaySingleplayer",
            "--userProperties",
            "--userType",
            "--username",
            "--uuid",
            "--version",
            "--versionType",
            "--width",
            "--xuid",
        }
    )
    CONTEXT_CONTROLLED_OPTIONS = {
        "--assetIndex": "assets_index_name",
        "--assetsDir": "assets_root",
        "--gameDir": "game_directory",
        "--version": "version_name",
        "--versionType": "version_type",
    }

    @classmethod
    def normalize(cls, arguments: list[str], context: dict) -> list[str]:
        entries = cls._parse(arguments)
        last_occurrence: dict[str, int] = {}
        for position, entry in enumerate(entries):
            option = entry[0]
            if option is not None:
                last_occurrence[option] = position

        normalized: list[str] = []
        for position, (option, value, raw) in enumerate(entries):
            if option is None:
                normalized.extend(raw)
                continue
            if last_occurrence[option] != position:
                continue

            canonical_value = cls._context_value(option, context)
            selected_value = canonical_value if canonical_value is not None else value
            if selected_value is None or not str(selected_value).strip():
                raise RuntimeError(f"Launch option {option} requires exactly one non-empty value.")
            normalized.extend((option, str(selected_value)))

        cls.validate(normalized)
        return normalized

    @classmethod
    def validate(cls, arguments: list[str]) -> None:
        counts: dict[str, int] = {}
        entries = cls._parse(arguments)
        for option, value, _raw in entries:
            if option is None:
                continue
            counts[option] = counts.get(option, 0) + 1
            if value is None or not str(value).strip():
                raise RuntimeError(f"Launch option {option} requires exactly one non-empty value.")

        duplicates = sorted(option for option, count in counts.items() if count > 1)
        if duplicates:
            joined = ", ".join(duplicates)
            raise RuntimeError(f"Launch command contains duplicate single-value options: {joined}.")

    @classmethod
    def _parse(cls, arguments: list[str]) -> list[tuple[str | None, str | None, list[str]]]:
        values = [str(argument) for argument in arguments]
        entries: list[tuple[str | None, str | None, list[str]]] = []
        index = 0
        while index < len(values):
            token = values[index]
            option, inline_value = cls._match_option(token)
            if option is None:
                entries.append((None, None, [token]))
                index += 1
                continue

            if inline_value is not None:
                entries.append((option, inline_value, [token]))
                index += 1
                continue

            value: str | None = None
            if index + 1 < len(values) and not cls._looks_like_option(values[index + 1]):
                value = values[index + 1]
                index += 2
            else:
                index += 1
            entries.append((option, value, [token] if value is None else [token, value]))
        return entries

    @classmethod
    def _match_option(cls, token: str) -> tuple[str | None, str | None]:
        if token in cls.SINGLE_VALUE_OPTIONS:
            return token, None
        if "=" not in token:
            return None, None
        option, value = token.split("=", 1)
        if option in cls.SINGLE_VALUE_OPTIONS:
            return option, value
        return None, None

    @classmethod
    def _looks_like_option(cls, token: str) -> bool:
        if token in cls.SINGLE_VALUE_OPTIONS:
            return True
        option = token.split("=", 1)[0]
        return option in cls.SINGLE_VALUE_OPTIONS or token.startswith("--")

    @classmethod
    def _context_value(cls, option: str, context: dict) -> str | None:
        key = cls.CONTEXT_CONTROLLED_OPTIONS.get(option)
        if key is None or key not in context:
            return None
        value = context.get(key)
        if value is None or not str(value).strip():
            return None
        return str(value)
