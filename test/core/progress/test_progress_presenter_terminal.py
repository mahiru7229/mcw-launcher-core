from src.gui.presenters.progress_presenter import ProgressPresenter
from src.models.progress.progress_event import ProgressEvent
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_state import ProgressState


def test_failed_event_has_terminal_failure_view() -> None:
    view = ProgressPresenter.present(ProgressEvent(stage=ProgressStage.CHECKING_MODPACK, message="modpack.update_check.failed", state=ProgressState.FAILED, detail="Network unavailable"))

    assert view.state is ProgressState.FAILED
    assert view.stage_text == "FAILED"
    assert view.percentage is None
    assert view.detail == "Network unavailable"


def test_success_event_has_ready_view() -> None:
    view = ProgressPresenter.present(ProgressEvent(stage=ProgressStage.SELECTING_JAVA, message="java.scan.completed", state=ProgressState.SUCCEEDED, detail="java.scan.completed_detail"))

    assert view.state is ProgressState.SUCCEEDED
    assert view.stage_text == "READY"
    assert view.percentage == 100
    assert view.detail == "Detected Java installations are now available in Launcher Settings."
