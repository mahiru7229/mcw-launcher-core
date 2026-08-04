from dataclasses import dataclass

from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_state import ProgressState
from src.models.progress.progress_unit import ProgressUnit


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: ProgressStage
    message: str

    current: int | None = None
    total: int | None = None

    unit: ProgressUnit = ProgressUnit.NONE
    bytes_per_second: float | None = None
    state: ProgressState = ProgressState.RUNNING
    detail: str = ""

    @property
    def remaining(self) -> int | None:
        if self.current is None or self.total is None:
            return None

        return max(int(self.total) - int(self.current), 0)

    @property
    def fraction(self) -> float | None:
        if self.current is None or self.total is None:
            return None

        if self.total <= 0:
            return None

        fraction = self.current / self.total

        return min(max(fraction, 0.0), 1.0)

    @property
    def percentage(self) -> float | None:
        fraction = self.fraction

        if fraction is None:
            return None

        return fraction * 100

    @property
    def is_determinate(self) -> bool:
        return self.fraction is not None

    @property
    def is_terminal(self) -> bool:
        return self.state in {ProgressState.SUCCEEDED, ProgressState.FAILED, ProgressState.CANCELLED}
