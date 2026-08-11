# MCW Core Library

Current distribution: **mcw-core 1.3.2**. This release adds Windows-safe atomic state publishing, update-integrity hardening, short-workspace cleanup guards, and rollback-safe package/theme operations without adding a GUI dependency.

MCW Core is the GUI-independent runtime used by MCW Launcher. It can be imported from a Python program without installing PySide6.

```python
from mcw_core import CorePaths, LaunchRequest, MCWCore

core = MCWCore(CorePaths.from_root(r"D:\\Games\\MCW"))
core.operations.begin()
try:
    result = core.launch(
        LaunchRequest(
            instance="My Quilt Instance",
            offline_username="Player",
            on_progress=print,
        )
    )
finally:
    core.operations.finish()

print(result.minecraft_version, result.java_path)
```

The same operation can be run without the GUI:

```powershell
python tools\core_smoke_launch.py --root D:\Games\MCW --instance "My Quilt Instance" --username Player
```

## Public API

The supported import surface is exposed from `mcw_core`:

- `MCWCore` and `CorePaths`
- `LaunchRequest` and `LaunchResult`
- `InstanceCreateRequest`
- `InstanceState`, `InstanceStatus`, and instance health reports
- `ProcessSession` and `ProcessSessionState`
- `OperationHandle`
- progress event models

Consumers should not import implementation modules from `src.core`.

## Process-wide paths

The current implementation keeps one active path configuration per Python process. Create one `MCWCore` for an application root, or explicitly call `configure_default_core()` before using the default facade.


## Instance health and process sessions

Runtime state and instance health are intentionally separate. Runtime state describes whether Minecraft is preparing, running, finished, or crashed. Health reports describe persistent problems such as invalid metadata, an unfinished transaction, a missing Java path, or a missing custom icon.

```python
report = core.instances.health("My Instance")
print(report.state, [issue.code for issue in report.issues])
```

Minecraft launches are supervised through persisted process-session records. Active records are reconciled during startup so a launcher interruption does not leave a permanent running badge or stale process metadata. Consumers can use the public `ProcessSession` and `ProcessSessionState` data models without importing implementation modules.
