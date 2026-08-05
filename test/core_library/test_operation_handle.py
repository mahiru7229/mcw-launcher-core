from mcw_core import OperationHandle
from src.core.network.download_pause import DownloadPauseController, DownloadCancelledError


def test_operation_handle_controls_headless_operation() -> None:
    controller = DownloadPauseController()
    handle = OperationHandle(controller)

    handle.begin()
    assert handle.state.active is True
    assert handle.pause() is True
    assert handle.state.paused is True
    assert handle.resume() is True
    assert handle.cancel() is True
    assert handle.state.cancel_requested is True

    try:
        handle.checkpoint()
    except DownloadCancelledError:
        pass
    else:
        raise AssertionError("Cancellation was not propagated through the public operation handle.")

    handle.finish()
    assert handle.state.active is False
