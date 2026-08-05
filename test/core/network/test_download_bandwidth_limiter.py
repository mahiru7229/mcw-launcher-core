from src.core.network.download_bandwidth_limiter import DownloadBandwidthLimiter


class FakeTime:
    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_limiter_is_disabled_by_default() -> None:
    fake = FakeTime()
    limiter = DownloadBandwidthLimiter(clock=fake.clock, sleeper=fake.sleep)

    limiter.throttle(4 * 1024 * 1024)

    assert limiter.is_enabled is False
    assert fake.sleeps == []


def test_limiter_caps_the_combined_stream_rate() -> None:
    fake = FakeTime()
    limiter = DownloadBandwidthLimiter(clock=fake.clock, sleeper=fake.sleep)
    limiter.configure_mbps(1.0)

    limiter.throttle(512 * 1024)
    limiter.throttle(512 * 1024)
    limiter.throttle(512 * 1024)

    assert limiter.limit_mbps == 1.0
    assert fake.sleeps == [0.5, 0.5, 0.5]


def test_limiter_zero_disables_and_resets_pending_delay() -> None:
    fake = FakeTime()
    limiter = DownloadBandwidthLimiter(clock=fake.clock, sleeper=fake.sleep)
    limiter.configure_mbps(1.0)
    limiter.throttle(1024 * 1024)
    fake.sleeps.clear()

    limiter.configure_mbps(0)
    limiter.throttle(1024 * 1024)

    assert limiter.is_enabled is False
    assert fake.sleeps == []


def test_limiter_normalizes_invalid_and_extreme_values() -> None:
    limiter = DownloadBandwidthLimiter()

    assert limiter.configure_mbps("invalid") == 0.0
    assert limiter.configure_mbps(-5) == 0.0
    assert limiter.configure_mbps(5000) == 1024.0
