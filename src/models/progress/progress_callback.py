from collections.abc import Callable

from src.models.progress.progress_event import ProgressEvent


ProgressCallback = Callable[[ProgressEvent], None]