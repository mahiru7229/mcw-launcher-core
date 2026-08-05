from src.core.progress.download_rate_meter import DownloadRateMeter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_rate_meter_calculates_bytes_per_second():
    clock = FakeClock()
    meter = DownloadRateMeter(initial_bytes=1024, clock=clock)

    clock.value = 2.0

    assert meter.update(5 * 1024) == 2 * 1024


def test_rate_meter_uses_recent_window_for_current_speed():
    clock = FakeClock()
    meter = DownloadRateMeter(clock=clock)

    clock.value = 1.0
    assert meter.update(1024) == 1024

    clock.value = 4.0
    assert meter.update(7 * 1024) == 2 * 1024


def test_rate_meter_returns_none_without_elapsed_transfer():
    clock = FakeClock()
    meter = DownloadRateMeter(clock=clock)

    assert meter.update(0) is None

    clock.value = 1.0
    assert meter.update(0) is None
