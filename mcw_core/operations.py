from __future__ import annotations

from dataclasses import dataclass

from src.core.network.download_pause import DownloadPauseController, download_pause_controller


@dataclass(frozen=True, slots=True)
class OperationState:
    active: bool
    paused: bool
    cancel_requested: bool


class OperationHandle:
    """GUI-independent cooperative pause, resume and cancel controls."""

    def __init__(self, controller: DownloadPauseController | None = None) -> None:
        self._controller = controller or download_pause_controller

    @property
    def state(self) -> OperationState:
        return OperationState(
            active=self._controller.is_active,
            paused=self._controller.is_paused,
            cancel_requested=self._controller.is_cancel_requested,
        )

    def begin(self) -> None:
        self._controller.begin()

    def finish(self) -> None:
        self._controller.finish()

    def pause(self) -> bool:
        return self._controller.request_pause()

    def resume(self) -> bool:
        return self._controller.request_resume()

    def cancel(self) -> bool:
        return self._controller.request_cancel()

    def checkpoint(self) -> None:
        self._controller.raise_if_requested()
