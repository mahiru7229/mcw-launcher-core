from contextlib import contextmanager
from collections.abc import Iterator

from src.models.progress.progress_callback import ProgressCallback
from src.models.progress.progress_event import ProgressEvent
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_state import ProgressState
from src.models.progress.progress_unit import ProgressUnit


class ProgressReporter:

    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self._callback = callback

    def report(self, stage: ProgressStage, message: str, current: int | None = None, total: int | None = None, unit: ProgressUnit = ProgressUnit.NONE, bytes_per_second: float | None = None, state: ProgressState = ProgressState.RUNNING, detail: str = "") -> None:
        if self._callback is None:
            return

        self._callback(
            ProgressEvent(
                stage=stage,
                message=message,
                current=current,
                total=total,
                unit=unit,
                bytes_per_second=bytes_per_second,
                state=state,
                detail=str(detail or ""),
            )
        )

    def status(self, stage: ProgressStage, message: str) -> None:
        self.report(stage=stage, message=message)

    def bytes(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None:
        self.report(stage=stage, message=message, current=current, total=total, unit=ProgressUnit.BYTES, bytes_per_second=bytes_per_second)

    def files(self, stage: ProgressStage, message: str, current: int, total: int, bytes_per_second: float | None = None) -> None:
        self.report(stage=stage, message=message, current=current, total=total, unit=ProgressUnit.FILES, bytes_per_second=bytes_per_second)

    def steps(self, stage: ProgressStage, message: str, current: int, total: int) -> None:
        self.report(stage=stage, message=message, current=current, total=total, unit=ProgressUnit.STEPS)

    def succeeded(self, stage: ProgressStage, message: str, detail: str = "") -> None:
        self.report(stage=stage, message=message, current=1, total=1, unit=ProgressUnit.STEPS, state=ProgressState.SUCCEEDED, detail=detail)

    def failed(self, stage: ProgressStage, message: str, detail: str = "") -> None:
        self.report(stage=stage, message=message, state=ProgressState.FAILED, detail=detail)

    def cancelled(self, stage: ProgressStage, message: str, detail: str = "") -> None:
        self.report(stage=stage, message=message, state=ProgressState.CANCELLED, detail=detail)

    @contextmanager
    def task(self, stage: ProgressStage, start_message: str, success_message: str, failure_message: str) -> Iterator[None]:
        self.status(stage, start_message)
        try:
            yield
        except Exception as error:
            self.failed(stage, failure_message, str(error))
            raise
        else:
            self.succeeded(stage, success_message)
