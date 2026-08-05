from src.core.progress.file_batch_progress import FileBatchProgress
from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_unit import ProgressUnit


def test_batch_progress_only_shows_speed_while_a_file_is_downloading() -> None:
    events = []
    reporter = ProgressReporter(events.append)
    batch = FileBatchProgress(reporter=reporter, stage=ProgressStage.DOWNLOADING_LIBRARIES, message="Preparing libraries...", total=2)
    first = object()

    batch.start()
    child = batch.reporter_for(first)
    assert child is not None
    child.bytes(stage=ProgressStage.DOWNLOADING_LIBRARIES, message="Downloading one.jar...", current=10, total=100, bytes_per_second=2 * 1024 * 1024)
    batch.complete(first)
    batch.complete(object())

    assert events[0].unit is ProgressUnit.FILES
    assert events[0].bytes_per_second is None
    assert events[1].bytes_per_second == 2 * 1024 * 1024
    assert events[-1].current == 2
    assert events[-1].bytes_per_second is None


def test_cached_files_never_add_a_fake_download_speed() -> None:
    events = []
    batch = FileBatchProgress(reporter=ProgressReporter(events.append), stage=ProgressStage.DOWNLOADING_ASSETS, message="Preparing assets...", total=2)

    batch.start()
    batch.complete(object())
    batch.complete(object())

    assert all(event.bytes_per_second is None for event in events)


def test_batch_progress_throttles_large_batches_but_always_reports_completion() -> None:
    now = [0.0]
    events = []
    batch = FileBatchProgress(
        reporter=ProgressReporter(events.append),
        stage=ProgressStage.DOWNLOADING_ASSETS,
        message="Preparing assets...",
        total=100,
        clock=lambda: now[0],
        min_emit_interval_seconds=0.1,
    )

    batch.start()
    for _ in range(10):
        batch.complete(object())

    assert [event.current for event in events] == [0]

    now[0] = 0.11
    batch.complete(object())
    assert [event.current for event in events] == [0, 11]

    for _ in range(89):
        batch.complete(object())

    assert events[-1].current == 100
    assert events[-1].percentage == 100
