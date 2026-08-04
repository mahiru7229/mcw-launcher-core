from __future__ import annotations

from src.core.instance.instance_run_lock import InstanceRunLock, RunningInstanceInfo
from src.models.instance.instance import Instance
from src.models.instance.instance_state import InstanceState, InstanceStatus


class InstanceStatusManager:
    @classmethod
    def resolve(cls, instance: Instance, running: RunningInstanceInfo | None = None) -> InstanceStatus:
        active = running or cls._find_running(instance)
        if active is not None:
            state = InstanceState.LOADING if active.state == "preparing" else InstanceState.RUNNING
            return InstanceStatus(
                instance_id=instance.instance_id,
                name=instance.name,
                state=state,
                launcher_pid=active.launcher_pid,
                minecraft_pid=active.minecraft_pid,
                last_played=instance.last_played,
                last_exit_code=instance.last_exit_code,
                last_launch_crashed=instance.last_launch_crashed,
                last_launch_state=instance.last_launch_state,
            )

        last_state = str(getattr(instance, "last_launch_state", "") or "").strip().casefold()
        if last_state == "crashed" or bool(getattr(instance, "last_launch_crashed", False)):
            state = InstanceState.CRASHED
        elif last_state == "finished" or bool(getattr(instance, "last_played", "")):
            state = InstanceState.FINISHED
        else:
            state = InstanceState.READY

        return InstanceStatus(
            instance_id=instance.instance_id,
            name=instance.name,
            state=state,
            last_played=instance.last_played,
            last_exit_code=instance.last_exit_code,
            last_launch_crashed=instance.last_launch_crashed,
            last_launch_state=instance.last_launch_state,
        )

    @classmethod
    def list(cls, instances: list[Instance]) -> list[InstanceStatus]:
        running = InstanceRunLock.list_active()
        running_by_id = {item.instance_id: item for item in running if item.instance_id}
        running_by_name = {item.name: item for item in running}
        return [cls.resolve(instance, running_by_id.get(instance.instance_id) or running_by_name.get(instance.name)) for instance in instances]

    @staticmethod
    def _find_running(instance: Instance) -> RunningInstanceInfo | None:
        for item in InstanceRunLock.list_active():
            if item.instance_id and item.instance_id == instance.instance_id:
                return item
            if item.name == instance.name:
                return item
        return None
