from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


class JavaRecoveryDiagnostics:
    """Bounded in-memory trace of automatic Java selection/provisioning decisions."""

    _events: deque[dict[str, Any]] = deque(maxlen=64)
    _lock = Lock()

    @classmethod
    def record(cls, event: str, **fields: object) -> None:
        row: dict[str, Any] = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": str(event or "").strip() or "unknown",
        }
        for key, value in fields.items():
            if isinstance(value, Path):
                row[str(key)] = str(value)
            elif value is not None:
                row[str(key)] = value
        with cls._lock:
            cls._events.append(row)

    @classmethod
    def snapshot(cls) -> tuple[dict[str, Any], ...]:
        with cls._lock:
            return tuple(dict(item) for item in cls._events)

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._events.clear()
