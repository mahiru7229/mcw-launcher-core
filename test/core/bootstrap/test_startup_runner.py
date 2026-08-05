from __future__ import annotations

from time import sleep

import pytest

from src.core.startup_runner import StartupTimeoutError, StartupWorkerError, run_startup_task


def test_startup_runner_forwards_progress_and_returns_result() -> None:
    progress: list[tuple[int, str]] = []
    pumps: list[bool] = []

    def task(report):
        report(25, "startup.loading_settings")
        report(80, "startup.protecting_accounts")
        return {"ready": True}

    result = run_startup_task(task, lambda percent, key: progress.append((percent, key)), lambda: pumps.append(True), timeout_seconds=1)

    assert result == {"ready": True}
    assert progress == [(25, "startup.loading_settings"), (80, "startup.protecting_accounts")]
    assert pumps


def test_startup_runner_preserves_worker_traceback() -> None:
    def task(_report):
        raise ValueError("broken startup data")

    with pytest.raises(StartupWorkerError) as raised:
        run_startup_task(task, lambda _percent, _key: None, lambda: None, timeout_seconds=1)

    assert isinstance(raised.value.original_error, ValueError)
    assert "broken startup data" in str(raised.value)
    assert "ValueError: broken startup data" in raised.value.traceback_text


def test_startup_runner_times_out_with_last_reported_stage() -> None:
    def task(report):
        report(62, "startup.preparing_accounts")
        sleep(0.25)
        return None

    with pytest.raises(StartupTimeoutError) as raised:
        run_startup_task(task, lambda _percent, _key: None, lambda: None, timeout_seconds=0.05)

    assert raised.value.stage_key == "startup.preparing_accounts"
    assert raised.value.timeout_seconds == pytest.approx(0.05)
