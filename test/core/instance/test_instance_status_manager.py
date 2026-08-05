from __future__ import annotations

from pathlib import Path

import pytest

from src.core.instance.instance_run_lock import InstanceRunLock, RunningInstanceInfo
from src.core.instance.instance_status_manager import InstanceStatusManager
from src.models.instance.instance import Instance
from src.models.instance.instance_state import InstanceState


def _instance(**changes) -> Instance:
    data = {
        "instance_id": "status-id",
        "name": "Status Test",
        "version_id": "1.20.1",
        "instance_dir": Path("instances/Status Test"),
        "mod_loader": ("vanilla", "-1"),
    }
    data.update(changes)
    return Instance(**data)


def _running(state: str) -> RunningInstanceInfo:
    return RunningInstanceInfo(
        instance_id="status-id",
        name="Status Test",
        state=state,
        launcher_pid=100,
        minecraft_pid=200 if state == "running" else None,
        created_at="2026-08-02T00:00:00+00:00",
        updated_at="2026-08-02T00:00:01+00:00",
    )


@pytest.mark.parametrize(
    ("instance", "running", "expected"),
    [
        (_instance(), None, InstanceState.READY),
        (_instance(last_played="2026-08-02T01:00:00+00:00"), None, InstanceState.FINISHED),
        (_instance(last_played="2026-08-02T01:00:00+00:00", last_launch_crashed=True, last_exit_code=1), None, InstanceState.CRASHED),
        (_instance(), _running("preparing"), InstanceState.LOADING),
        (_instance(last_launch_crashed=True), _running("running"), InstanceState.RUNNING),
    ],
)
def test_status_precedence(instance: Instance, running: RunningInstanceInfo | None, expected: InstanceState) -> None:
    status = InstanceStatusManager.resolve(instance, running)
    assert status.state is expected


def test_list_uses_active_lock_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(InstanceRunLock, "list_active", classmethod(lambda cls: [_running("running")]))
    statuses = InstanceStatusManager.list([_instance(last_launch_crashed=True)])
    assert [status.state for status in statuses] == [InstanceState.RUNNING]
    assert statuses[0].minecraft_pid == 200
