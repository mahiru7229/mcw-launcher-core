from __future__ import annotations

from collections.abc import Iterable
import re


_MINECRAFT_RELEASE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def provider_game_version_rank(target_version: str, declared_versions: Iterable[str]) -> int:
    """Rank advisory provider metadata without rejecting any version."""
    target = str(target_version).strip()
    declared = tuple(
        dict.fromkeys(
            str(version).strip()
            for version in declared_versions
            if str(version).strip()
        )
    )
    if not target or target in declared:
        return 0
    if _release_line(target) in {
        line
        for version in declared
        if (line := _release_line(version)) is not None
    }:
        return 1
    if not declared:
        return 2
    return 3


def _release_line(version: str) -> tuple[int, int] | None:
    match = _MINECRAFT_RELEASE.fullmatch(str(version).strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))
