# MCW Core Library

Standalone Stable source runtime for MCW Launcher **v1.6.0**. This package is the headless Core distribution and does not include the PySide6 launcher GUI.

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

### LaunchRequest — v1.6.0 additions

| Field | Type | Default | Description |
|---|---|---|---|
| `quick_play_singleplayer` | `str` | `""` | World name to open directly (Java Edition Quick Play). |
| `quick_play_multiplayer` | `str` | `""` | `host:port` to connect to directly on launch. |
| `on_window_ready` | `Callable[[int], None] \| None` | `None` | Callback receiving the native window handle once the game window is visible. |

```python
result = core.launch(
    LaunchRequest(
        instance="Survival",
        offline_username="Player",
        quick_play_singleplayer="My World",
        on_window_ready=lambda hwnd: print("Game window HWND:", hwnd),
    )
)
```

### InstanceCreateRequest — v1.6.0 additions

| Field | Type | Default | Description |
|---|---|---|---|
| `jvm_arguments` | `tuple[str, ...]` | `()` | Extra JVM flags applied to the new instance's `settings.json`. |

```python
from mcw_core import InstanceCreateRequest, get_default_core

instance = get_default_core().instances.create(
    InstanceCreateRequest(
        name="OptiFine Pack",
        version_id="1.20.1",
        loader_name="forge",
        jvm_arguments=("-XX:+UseG1GC", "-XX:MaxGCPauseMillis=200"),
    )
)
```

### New public API modules — v1.6.0

| Module | Description |
|---|---|
| `mcw_core.api.integrations.discord` | Discord Rich Presence bridge. |
| `mcw_core.api.diagnostics.mclogs_client` | MCLogs.app log upload client. |
| `mcw_core.api.java.jvm_presets` | Built-in JVM argument preset helpers. |
| `mcw_core.api.minecraft.screenshot_manager` | Screenshot folder and file management. |
| `mcw_core.api.minecraft.world_manager` | World save enumeration and management. |

## Process-wide paths

The current implementation keeps one active path configuration per Python process. Create one `MCWCore` for an application root, or explicitly call `configure_default_core()` before using the default facade.


## Instance health and process sessions

Runtime state and instance health are intentionally separate. Runtime state describes whether Minecraft is preparing, running, finished, or crashed. Health reports describe persistent problems such as invalid metadata, an unfinished transaction, a missing Java path, or a missing custom icon.

```python
report = core.instances.health("My Instance")
print(report.state, [issue.code for issue in report.issues])
```

Minecraft launches are supervised through persisted process-session records. Active records are reconciled during startup so a launcher interruption does not leave a permanent running badge or stale process metadata. Consumers can use the public `ProcessSession` and `ProcessSessionState` data models without importing implementation modules.
