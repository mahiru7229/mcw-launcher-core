# MCW Core Library

Standalone Stable runtime and JSON-RPC 2.0 server for MCW Launcher **v1.8.0**. MCW Core is published as a standalone library and wheel package (`mcw_core-1.8.0-py3-none-any.whl`) via [MCW Launcher Core](https://github.com/mahiru7229/mcw-launcher-core).

MCW Core is the 100% GUI-independent runtime used by MCW Launcher. It can be imported from a Python program without installing PySide6, or driven from any programming language (TypeScript/React, Rust/Tauri, C#, Go) via **JSON-RPC 2.0** (`mcw_core.rpc`).

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

## JSON-RPC 2.0 Interface (`mcw_core.rpc`) — v1.8.0

Starting in **v1.8.0**, `mcw_core.rpc` provides a complete JSON-RPC 2.0 interface over three transports:

1. **Direct JSON Bridge (`mode="direct"`)**: In-process JSON serialization/deserialization through `CoreRpcDispatcher.handle_json()`.
2. **Stdio Sidecar (`mode="stdio"` / `mcw-core-rpc --stdio`)**: Line-delimited JSON-RPC 2.0 over `stdin`/`stdout` for Sidecar child processes.
3. **Local HTTP + SSE Server (`mode="http"` / `mcw-core-rpc --http`)**: HTTP server on `127.0.0.1` with `GET /health`, `POST /rpc`, and `GET /events` (Server-Sent Events).

```python
from mcw_core.rpc import CoreRpcClient

client = CoreRpcClient(mode="direct", data_root=r"D:\\Games\\MCW")
print(client.call("system.ping"))
print(client.call("instances.list"))
client.close()
```

## Public API

The supported import surface is exposed from `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, and `mcw_core.api.models.*`:

- `MCWCore` and `CorePaths`
- `CoreRpcClient`, `CoreRpcDispatcher`, `HttpRpcServer`, `StdioRpcServer`, `RpcRequest`, `RpcResponse`, `RpcEvent`
- `LaunchRequest` and `LaunchResult`
- `InstanceCreateRequest`
- `InstanceState`, `InstanceStatus`, and instance health reports
- `ProcessSession` and `ProcessSessionState`
- `OperationHandle`
- `mcw_core.api.models.*` (all domain models)

Consumers and GUIs must not import implementation modules from `src.core` or `src.models`.

### LaunchRequest — v1.6.0+ additions

| Field | Type | Default | Description |
|---|---|---|---|
| `quick_play_singleplayer` | `str` | `""` | World name to open directly (Java Edition Quick Play). |
| `quick_play_multiplayer` | `str` | `""` | `host:port` to connect to directly on launch. |
| `on_window_ready` | `Callable[[int], None] \| None` | `None` | Callback receiving the native window handle once the game window is visible. |

### InstanceCreateRequest — v1.6.0+ additions

| Field | Type | Default | Description |
|---|---|---|---|
| `jvm_arguments` | `tuple[str, ...]` | `()` | Extra JVM flags applied to the new instance's `settings.json`. |

### Public API modules (`v1.6.0` – `v1.8.0`)

| Module | Description |
|---|---|
| `mcw_core.rpc` | JSON-RPC 2.0 Dispatcher, Client, Stdio Sidecar Server, and Local HTTP + SSE Server. |
| `mcw_core.api.models.*` | Complete public re-exports of all domain and progress models. |
| `mcw_core.api.update.hotfix_manager` | Cloudflare Edge CDN dynamic hotfix manager (`HotfixManager`, `HotfixMetaPathFinder`). |
| `mcw_core.api.hardware.gpu_preference_manager` | Hardware GPU detection with persistent startup caching. |
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
