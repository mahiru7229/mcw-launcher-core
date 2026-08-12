from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GameExitResult:
    instance_name: str
    minecraft_version: str
    pid: int | None
    exit_code: int
    started_at: str
    ended_at: str
    duration_seconds: int
    crashed: bool
    session_id: str | None = None
    stopped_by_launcher: bool = False
    killed_by_user: bool = False
    log_path: Path | None = None
    crash_report_path: Path | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["log_path"] = str(self.log_path) if self.log_path is not None else None
        data["crash_report_path"] = str(self.crash_report_path) if self.crash_report_path is not None else None
        return data
