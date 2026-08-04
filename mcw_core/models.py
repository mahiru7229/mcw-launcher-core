from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Mapping, Iterator
from typing import Any

from src.models.account.account import Account
from src.models.auth.authentication import Authentication
from src.models.instance.instance import Instance
from src.models.progress.progress_callback import ProgressCallback
from src.models.runtime.game_exit_result import GameExitResult


@dataclass(frozen=True, slots=True)
class LaunchRequest:
    """Headless launch request accepted by the public MCW Core API.

    ``instance`` may be an already loaded :class:`Instance` or its name.  A
    caller may provide an authenticated account pair, or simply set
    ``offline_username`` for an offline launch.
    """

    instance: Instance | str
    account: Account | None = None
    authentication: Authentication | None = None
    offline_username: str = ""
    debug_mode: bool = False
    on_progress: ProgressCallback | None = None
    on_exit: Callable[[GameExitResult], None] | None = None
    allow_compatibility_issues_once: bool = False


@dataclass(frozen=True, slots=True)
class LaunchResult(Mapping[str, Any]):
    java_path: Path
    minecraft_java_major_version: int
    minecraft_version: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "javaPath": self.java_path,
            "minecraftJavaMajorVersion": self.minecraft_java_major_version,
            "minecraftVersion": self.minecraft_version,
        }
        if self.warnings:
            result["warnings"] = self.warnings
        return result

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.as_dict())

    def __len__(self) -> int:
        return len(self.as_dict())

    @classmethod
    def from_legacy(cls, result: Mapping[str, Any]) -> "LaunchResult":
        return cls(
            java_path=Path(result["javaPath"]),
            minecraft_java_major_version=int(result["minecraftJavaMajorVersion"]),
            minecraft_version=str(result["minecraftVersion"]),
            warnings=tuple(str(item) for item in result.get("warnings", ()) or ()),
        )


@dataclass(frozen=True, slots=True)
class InstanceCreateRequest:
    name: str
    version_id: str
    loader_name: str = "vanilla"
    loader_version: str = "auto"
    on_progress: ProgressCallback | None = None
