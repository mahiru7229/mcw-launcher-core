import pytest

from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_event import ProgressEvent
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_state import ProgressState
from src.models.progress.progress_unit import ProgressUnit


def test_report_does_nothing_without_callback():
    reporter = ProgressReporter()

    result = reporter.report(
        stage=ProgressStage.PREPARING,
        message="Preparing",
    )

    assert result is None


def test_report_sends_progress_event_to_callback():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.report(
        stage=ProgressStage.DOWNLOADING_ASSETS,
        message="Downloading assets",
        current=25,
        total=100,
        unit=ProgressUnit.FILES,
    )

    assert len(received) == 1

    event = received[0]

    assert isinstance(event, ProgressEvent)
    assert event.stage is ProgressStage.DOWNLOADING_ASSETS
    assert event.message == "Downloading assets"
    assert event.current == 25
    assert event.total == 100
    assert event.unit is ProgressUnit.FILES


def test_report_uses_default_values():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.report(
        stage=ProgressStage.PREPARING,
        message="Preparing",
    )

    event = received[0]

    assert event.current is None
    assert event.total is None
    assert event.unit is ProgressUnit.NONE


def test_status_reports_indeterminate_event():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.status(
        stage=ProgressStage.BUILDING_CONTEXT,
        message="Building context",
    )

    event = received[0]

    assert event.stage is ProgressStage.BUILDING_CONTEXT
    assert event.message == "Building context"
    assert event.current is None
    assert event.total is None
    assert event.unit is ProgressUnit.NONE
    assert event.is_determinate is False


def test_bytes_reports_byte_progress():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.bytes(
        stage=ProgressStage.DOWNLOADING_CLIENT,
        message="Downloading client",
        current=512,
        total=1024,
        bytes_per_second=256.0,
    )

    event = received[0]

    assert event.stage is ProgressStage.DOWNLOADING_CLIENT
    assert event.current == 512
    assert event.total == 1024
    assert event.unit is ProgressUnit.BYTES
    assert event.bytes_per_second == 256.0
    assert event.remaining == 512
    assert event.fraction == 0.5
    assert event.percentage == 50.0
    assert event.is_determinate is True


def test_files_reports_file_progress():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.files(
        stage=ProgressStage.DOWNLOADING_LIBRARIES,
        message="Downloading libraries",
        current=3,
        total=10,
    )

    event = received[0]

    assert event.stage is ProgressStage.DOWNLOADING_LIBRARIES
    assert event.current == 3
    assert event.total == 10
    assert event.unit is ProgressUnit.FILES
    assert event.fraction == 0.3
    assert event.percentage == 30.0


def test_report_preserves_event_order():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.status(
        ProgressStage.PREPARING,
        "Preparing",
    )
    reporter.files(
        ProgressStage.DOWNLOADING_LIBRARIES,
        "Libraries",
        2,
        5,
    )
    reporter.status(
        ProgressStage.FINISHED,
        "Finished",
    )

    assert [
        event.stage
        for event in received
    ] == [
        ProgressStage.PREPARING,
        ProgressStage.DOWNLOADING_LIBRARIES,
        ProgressStage.FINISHED,
    ]


def test_callback_exception_is_not_swallowed():
    def failing_callback(event: ProgressEvent) -> None:
        raise RuntimeError("callback failed")

    reporter = ProgressReporter(failing_callback)

    with pytest.raises(
        RuntimeError,
        match="callback failed",
    ):
        reporter.status(
            ProgressStage.PREPARING,
            "Preparing",
        )


def test_progress_event_fraction_is_none_without_current():
    event = ProgressEvent(
        stage=ProgressStage.PREPARING,
        message="Preparing",
        current=None,
        total=100,
    )

    assert event.fraction is None
    assert event.percentage is None
    assert event.is_determinate is False


def test_progress_event_fraction_is_none_without_total():
    event = ProgressEvent(
        stage=ProgressStage.PREPARING,
        message="Preparing",
        current=10,
        total=None,
    )

    assert event.fraction is None
    assert event.percentage is None
    assert event.is_determinate is False


@pytest.mark.parametrize(
    "total",
    [
        0,
        -1,
        -100,
    ],
)
def test_progress_event_fraction_is_none_for_non_positive_total(
    total: int,
):
    event = ProgressEvent(
        stage=ProgressStage.DOWNLOADING_ASSETS,
        message="Assets",
        current=10,
        total=total,
    )

    assert event.fraction is None
    assert event.percentage is None
    assert event.is_determinate is False


@pytest.mark.parametrize(
    (
        "current",
        "total",
        "expected_fraction",
        "expected_percentage",
    ),
    [
        (0, 100, 0.0, 0.0),
        (1, 4, 0.25, 25.0),
        (50, 100, 0.5, 50.0),
        (100, 100, 1.0, 100.0),
    ],
)
def test_progress_event_calculates_fraction_and_percentage(
    current: int,
    total: int,
    expected_fraction: float,
    expected_percentage: float,
):
    event = ProgressEvent(
        stage=ProgressStage.DOWNLOADING_CLIENT,
        message="Client",
        current=current,
        total=total,
        unit=ProgressUnit.BYTES,
    )

    assert event.fraction == expected_fraction
    assert event.percentage == expected_percentage
    assert event.is_determinate is True


def test_progress_event_clamps_negative_current_to_zero():
    event = ProgressEvent(
        stage=ProgressStage.DOWNLOADING_ASSETS,
        message="Assets",
        current=-10,
        total=100,
    )

    assert event.fraction == 0.0
    assert event.percentage == 0.0


def test_progress_event_clamps_current_above_total_to_one():
    event = ProgressEvent(
        stage=ProgressStage.DOWNLOADING_ASSETS,
        message="Assets",
        current=150,
        total=100,
    )

    assert event.fraction == 1.0
    assert event.percentage == 100.0


def test_progress_event_is_frozen():
    event = ProgressEvent(
        stage=ProgressStage.PREPARING,
        message="Preparing",
    )

    with pytest.raises(Exception):
        event.message = "Changed"


def test_all_progress_stages_have_unique_values():
    values = [
        stage.value
        for stage in ProgressStage
    ]

    assert len(values) == len(set(values))


def test_all_progress_units_have_unique_values():
    values = [
        unit.value
        for unit in ProgressUnit
    ]

    assert len(values) == len(set(values))


@pytest.mark.parametrize(
    (
        "unit",
        "value",
    ),
    [
        (ProgressUnit.NONE, "none"),
        (ProgressUnit.BYTES, "bytes"),
        (ProgressUnit.FILES, "files"),
        (ProgressUnit.STEPS, "steps"),
    ],
)
def test_progress_unit_values_are_stable(
    unit: ProgressUnit,
    value: str,
):
    assert unit.value == value


@pytest.mark.parametrize(
    (
        "stage",
        "value",
    ),
    [
        (ProgressStage.PREPARING, "preparing"),
        (
            ProgressStage.LOADING_VERSION,
            "loading_version",
        ),
        (
            ProgressStage.DOWNLOADING_CLIENT,
            "downloading_client",
        ),
        (
            ProgressStage.DOWNLOADING_LIBRARIES,
            "downloading_libraries",
        ),
        (
            ProgressStage.DOWNLOADING_ASSET_INDEX,
            "downloading_asset_index",
        ),
        (
            ProgressStage.DOWNLOADING_ASSETS,
            "downloading_assets",
        ),
        (
            ProgressStage.BUILDING_CONTEXT,
            "building_context",
        ),
        (
            ProgressStage.BUILDING_COMMAND,
            "building_command",
        ),
        (
            ProgressStage.SELECTING_JAVA,
            "selecting_java",
        ),
        (
            ProgressStage.LAUNCHING,
            "launching",
        ),
        (
            ProgressStage.FINISHED,
            "finished",
        ),
    ],
)
def test_progress_stage_values_are_stable(
    stage: ProgressStage,
    value: str,
):
    assert stage.value == value

def test_progress_event_remaining_never_becomes_negative():
    event = ProgressEvent(
        stage=ProgressStage.DOWNLOADING_CLIENT,
        message="Client",
        current=120,
        total=100,
        unit=ProgressUnit.BYTES,
    )

    assert event.remaining == 0


def test_files_can_report_aggregate_download_speed():
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.files(
        stage=ProgressStage.DOWNLOADING_LIBRARIES,
        message="Downloading libraries",
        current=2,
        total=5,
        bytes_per_second=1024.0,
    )

    event = received[0]
    assert event.unit is ProgressUnit.FILES
    assert event.bytes_per_second == 1024.0


def test_terminal_helpers_emit_explicit_states() -> None:
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    reporter.succeeded(ProgressStage.FINISHED, "done", "ready")
    reporter.failed(ProgressStage.CHECKING_MODPACK, "failed", "network")
    reporter.cancelled(ProgressStage.DOWNLOADING_MODS, "cancelled")

    assert [event.state for event in received] == [ProgressState.SUCCEEDED, ProgressState.FAILED, ProgressState.CANCELLED]
    assert all(event.is_terminal for event in received)
    assert received[0].percentage == 100.0
    assert received[1].detail == "network"


def test_task_context_reports_failure_before_reraising() -> None:
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    with pytest.raises(RuntimeError, match="boom"):
        with reporter.task(ProgressStage.CHECKING_MODPACK, "start", "done", "failed"):
            raise RuntimeError("boom")

    assert [event.message for event in received] == ["start", "failed"]
    assert received[-1].state is ProgressState.FAILED
    assert received[-1].detail == "boom"


def test_task_context_reports_success() -> None:
    received: list[ProgressEvent] = []
    reporter = ProgressReporter(received.append)

    with reporter.task(ProgressStage.SELECTING_JAVA, "start", "done", "failed"):
        pass

    assert received[-1].state is ProgressState.SUCCEEDED
    assert received[-1].message == "done"
