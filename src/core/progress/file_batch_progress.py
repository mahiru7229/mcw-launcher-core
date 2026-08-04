from __future__ import annotations

from collections.abc import Callable
from threading import Lock
import time

from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage


class FileBatchProgress:
    ACTIVE_RATE_TTL_SECONDS = 3.0

    def __init__(self, reporter: ProgressReporter | None, stage: ProgressStage, message: str, total: int, clock: Callable[[], float] | None = None, min_emit_interval_seconds: float = 0.0) -> None:
        self._reporter = reporter
        self._stage = stage
        self._message = message
        self._total = max(0, int(total))
        self._clock = clock or time.monotonic
        self._min_emit_interval_seconds = max(0.0, float(min_emit_interval_seconds))
        self._completed = 0
        self._rates: dict[object, tuple[float, float]] = {}
        self._last_emit_at = float("-inf")
        self._lock = Lock()

    def start(self) -> None:
        self._emit(current=0, bytes_per_second=None, force=True)

    def reporter_for(self, token: object) -> "_FileBatchReporter" | None:
        if self._reporter is None or not callable(getattr(self._reporter, "bytes", None)):
            return None
        return _FileBatchReporter(self, token)

    def complete(self, token: object) -> None:
        with self._lock:
            speed = self._aggregate_speed_locked()
            self._rates.pop(token, None)
            self._completed = min(self._completed + 1, self._total)
            current = self._completed
        self._emit(current=current, bytes_per_second=speed, force=self._total <= 20 or current >= self._total)

    def discard(self, token: object) -> None:
        with self._lock:
            removed = self._rates.pop(token, None) is not None
            current = self._completed
            speed = self._aggregate_speed_locked()
        if removed:
            self._emit(current=current, bytes_per_second=speed)

    def update_speed(self, token: object, bytes_per_second: float | None) -> None:
        speed = float(bytes_per_second or 0.0)
        with self._lock:
            changed = False
            if speed > 0:
                self._rates[token] = (speed, self._clock())
                changed = True
            elif token in self._rates:
                self._rates.pop(token, None)
                changed = True

            if not changed:
                return

            current = self._completed
            aggregate_speed = self._aggregate_speed_locked()
        self._emit(current=current, bytes_per_second=aggregate_speed)

    def _aggregate_speed_locked(self) -> float | None:
        now = self._clock()
        stale_tokens = [token for token, (_, updated_at) in self._rates.items() if now - updated_at > self.ACTIVE_RATE_TTL_SECONDS]
        for token in stale_tokens:
            self._rates.pop(token, None)

        total_speed = sum(speed for speed, _ in self._rates.values())
        return total_speed if total_speed > 0 else None

    def _emit(self, current: int, bytes_per_second: float | None, force: bool = False) -> None:
        if self._reporter is None:
            return

        now = self._clock()
        with self._lock:
            if not force and self._min_emit_interval_seconds > 0 and now - self._last_emit_at < self._min_emit_interval_seconds:
                return
            self._last_emit_at = now

        kwargs = {"stage": self._stage, "message": self._message, "current": current, "total": self._total}
        if bytes_per_second is not None and bytes_per_second > 0:
            kwargs["bytes_per_second"] = bytes_per_second
        self._reporter.files(**kwargs)


class _FileBatchReporter:
    def __init__(self, batch: FileBatchProgress, token: object) -> None:
        self._batch = batch
        self._token = token

    def bytes(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None:
        self._batch.update_speed(self._token, bytes_per_second)
