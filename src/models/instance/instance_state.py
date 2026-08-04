from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class InstanceState(StrEnum):
    READY = "ready"
    LOADING = "loading"
    RUNNING = "running"
    FINISHED = "finished"
    CRASHED = "crashed"


@dataclass(frozen=True, slots=True)
class InstanceStatus:
    instance_id: str
    name: str
    state: InstanceState
    launcher_pid: int | None = None
    minecraft_pid: int | None = None
    last_played: str = ""
    last_exit_code: int | None = None
    last_launch_crashed: bool = False
    last_launch_state: str = "ready"
