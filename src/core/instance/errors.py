from __future__ import annotations

from pathlib import Path


class InstanceAlreadyRunningError(RuntimeError):
    def __init__(self, instance_name: str) -> None:
        self.instance_name = instance_name
        super().__init__(f"Instance '{instance_name}' is already running. Close Minecraft before launching this instance again.")


class InstanceModChangeBlockedError(RuntimeError):
    def __init__(self, instance_name: str) -> None:
        self.instance_name = instance_name
        super().__init__(f"Cannot change mods while instance '{instance_name}' is running.")


class InstanceDeletionError(RuntimeError):
    """Structured failure raised when an instance cannot be removed safely."""

    def __init__(
        self,
        instance_name: str,
        instance_dir: Path,
        locked_path: Path | None,
        attempts: int,
        processes: tuple[tuple[int, str, str], ...] = (),
        winerror: int | None = None,
        detail: str = "",
        scheduled: bool = False,
    ) -> None:
        self.instance_name = str(instance_name)
        self.instance_dir = Path(instance_dir)
        self.locked_path = Path(locked_path) if locked_path is not None else None
        self.attempts = max(0, int(attempts))
        self.processes = tuple(processes)
        self.winerror = int(winerror) if isinstance(winerror, int) else None
        self.detail = str(detail or "").strip()
        self.scheduled = bool(scheduled)

        path_text = str(self.locked_path or self.instance_dir)
        process_text = ""
        if self.processes:
            labels = [f"{name or 'process'} (PID {pid})" for pid, name, _command in self.processes]
            process_text = f" Locking process: {', '.join(labels)}."
        code_text = f" WinError {self.winerror}." if self.winerror is not None else ""
        if self.detail:
            action = self.detail
        elif self.scheduled:
            action = "Deletion was queued for the next launcher startup. The instance registry was not removed yet."
        else:
            action = "Close the related helper process and retry. The instance registry was not removed."
        super().__init__(
            f"Could not delete instance '{self.instance_name}' after {self.attempts} attempt(s). "
            f"Locked path: {path_text}.{code_text}{process_text} {action}"
        )
