from __future__ import annotations

from threading import Condition, RLock
from time import monotonic


class DownloadInterruptedError(RuntimeError):
    """Base class for cooperative download interruption requests."""


class DownloadPausedError(DownloadInterruptedError):
    """Legacy terminal pause error kept for compatibility with older callers."""


class DownloadCancelledError(DownloadPausedError):
    """Raised when the user cancels the active launcher download session."""


class DownloadPauseController:
    def __init__(self) -> None:
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._active = False
        self._paused = False
        self._cancel_requested = False

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def is_pause_requested(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def is_cancel_requested(self) -> bool:
        with self._lock:
            return self._cancel_requested

    def begin(self) -> None:
        with self._condition:
            self._paused = False
            self._cancel_requested = False
            self._active = True
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self._active = False
            self._paused = False
            self._cancel_requested = False
            self._condition.notify_all()

    def request_pause(self) -> bool:
        with self._condition:
            if not self._active or self._paused or self._cancel_requested:
                return False
            self._paused = True
            self._condition.notify_all()
            return True

    def request_resume(self) -> bool:
        with self._condition:
            if not self._active or not self._paused or self._cancel_requested:
                return False
            self._paused = False
            self._condition.notify_all()
            return True

    def request_cancel(self) -> bool:
        with self._condition:
            if not self._active or self._cancel_requested:
                return False
            self._cancel_requested = True
            self._paused = False
            self._condition.notify_all()
            return True

    def raise_if_requested(self) -> None:
        """Block while paused and raise only when cancellation is requested."""
        with self._condition:
            while self._active and self._paused and not self._cancel_requested:
                self._condition.wait(timeout=0.25)
            if self._active and self._cancel_requested:
                raise DownloadCancelledError("Download cancelled by user.")

    def wait(self, seconds: float) -> None:
        """Cooperative delay that respects pause, resume, and cancel requests."""
        deadline = monotonic() + max(0.0, float(seconds))
        with self._condition:
            while True:
                while self._active and self._paused and not self._cancel_requested:
                    self._condition.wait(timeout=0.25)
                if self._active and self._cancel_requested:
                    raise DownloadCancelledError("Download cancelled by user.")
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return
                self._condition.wait(timeout=min(remaining, 0.25))


def _contains_error(error: BaseException | None, error_type: type[BaseException]) -> bool:
    current = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        if isinstance(current, error_type):
            return True
        visited.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def is_download_paused(error: BaseException | None) -> bool:
    """Compatibility helper; cancellation is also an interrupted download."""
    return _contains_error(error, DownloadPausedError)


def is_download_cancelled(error: BaseException | None) -> bool:
    return _contains_error(error, DownloadCancelledError)


download_pause_controller = DownloadPauseController()
