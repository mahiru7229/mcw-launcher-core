from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ProcessSessionState(StrEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    STOPPING = "stopping"
    FINISHED = "finished"
    CRASHED = "crashed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class ProcessSession:
    session_id: str
    instance_id: str
    instance_name: str
    instance_dir: Path
    state: ProcessSessionState
    launcher_pid: int | None
    root_pid: int | None
    child_pids: tuple[int, ...]
    started_at: str
    updated_at: str
    ended_at: str = ""
    exit_code: int | None = None
    detail: str = ""

    @property
    def active(self) -> bool:
        return self.state in {
            ProcessSessionState.PREPARING,
            ProcessSessionState.RUNNING,
            ProcessSessionState.STOPPING,
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "instance_id": self.instance_id,
            "instance_name": self.instance_name,
            "instance_dir": str(self.instance_dir),
            "state": self.state.value,
            "launcher_pid": self.launcher_pid,
            "root_pid": self.root_pid,
            "child_pids": list(self.child_pids),
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "exit_code": self.exit_code,
            "detail": self.detail,
        }
