# MCW Core 1.8.0

MCW Core is the headless engine runtime shipped with MCW Launcher `v1.8.0`. This source distribution contains the complete public API, JSON-RPC 2.0 server (`mcw_core.rpc`), implementation, data models, tests, documentation, examples, and LAN Agent resource. The separate CurseForge gateway source archive is intentionally not bundled with MCW Core.

PySide6 and the launcher GUI are intentionally not part of the Core distribution.

## What changed in 1.8.0

- **100% Core & GUI Decoupling via JSON-RPC 2.0 (`mcw_core.rpc`)**:
  - Added `CoreRpcDispatcher` providing a language-agnostic JSON-RPC 2.0 gateway for all Core domains (`system.*`, `instances.*`, `java.*`, `content.*`, `catalog.*`, `worlds.*`, `screenshots.*`, `diagnostics.*`, `operations.*`).
  - Added **Stdio Sidecar Server (`StdioRpcServer`)** via `mcw-core-rpc --stdio` (or `python -m mcw_core.rpc.cli --stdio`) for out-of-process integration with Tauri v2 (Rust + TypeScript/React), Electron, C#, or CLI tools.
  - Added **Local HTTP + Server-Sent Events Server (`HttpRpcServer`)** via `mcw-core-rpc --http` on `127.0.0.1` with `GET /health`, `POST /rpc`, and real-time event streaming over `GET /events` (SSE).
  - Added multi-transport `CoreRpcClient` supporting `mode="direct"`, `mode="http"`, and `mode="stdio"`.
- **Complete Public API & Models Surface (`mcw_core/api/` & `mcw_core/api/models/`)**:
  - Exported 100% of Core services and domain models under `mcw_core.api.*` and `mcw_core.api.models.*` so external GUIs never need to import internal `src.core.*` or `src.models.*` modules.
- **Dynamic Hotfix Engine & Hardware GPU Caching (merged from `1.7.0` – `1.7.1.1`)**:
  - Added `HotfixManager` and `HotfixMetaPathFinder` (`mcw_core.api.update.hotfix_manager`) for SHA-256 verified runtime hotfix patching from Cloudflare Edge CDN (`mcw-download.pages.dev`) with atomic directory swaps and automatic cleanup on base version upgrades.
  - Added hardware GPU detection caching in `GpuPreferenceManager` (`mcw_core.api.hardware.gpu_preference_manager`) for fast startup.

## What changed in 1.6.1

- **Modloader metadata network retries**: Added `HttpDownloader.get_with_retry` with at least 5 attempts and exponential backoff for Forge, NeoForge, Fabric, and Quilt metadata clients to survive transient network timeouts or connection drops.
- **Extended Windows path support (`\\?\`)**: Extended `src/core/fs/windows_path.py` with `to_extended_windows_path()` and `native_filesystem_path()`, adding support in `copy_file()`, `link_file()`, `same_file()`, `open_file()`, and `is_file()` to handle paths exceeding 260 characters (`MAX_PATH`).
- **Long-path protection in Java & Loader managers**: `JavaProvisioner`, `NeoForgeVersionManager`, and `ForgeVersionManager` safely handle deep nested library extractions, chunked streaming copy fallbacks, and runtime markers (fixes Issue #32).
- **Staging publishing optimization**: Shortened temporary publishing artifact filenames in `SharedFileMaterializer` (`.tmp_<hex>.pub`), saving up to 90 path characters.

## Installation

### From prebuilt Wheel (`.whl`)

```bash
pip install mcw_core-1.8.0-py3-none-any.whl
```

### Install for development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest test -q
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## JSON-RPC 2.0 Server & Client Usage (v1.8.0)

### 1. Run as a Stdio Sidecar Process (for Tauri / TypeScript / C#)

```bash
mcw-core-rpc --stdio --root ./mcw-data
```

Send line-delimited JSON-RPC 2.0 requests to `stdin`:

```json
{"jsonrpc": "2.0", "id": 1, "method": "system.ping", "params": {}}
```

### 2. Run as a Local HTTP + SSE Daemon

```bash
mcw-core-rpc --http --host 127.0.0.1 --port 45180 --root ./mcw-data
```

- `GET http://127.0.0.1:45180/health` — Readiness & version probe
- `POST http://127.0.0.1:45180/rpc` — JSON-RPC 2.0 command endpoint
- `GET http://127.0.0.1:45180/events` — Server-Sent Events (SSE) real-time progress stream

### 3. Python `CoreRpcClient` (Direct, HTTP, or Stdio Sidecar)

```python
from mcw_core.rpc import CoreRpcClient

client = CoreRpcClient(mode="direct", data_root="./mcw-data")
print(client.call("system.ping"))
print(client.call("instances.list"))
client.close()
```

## Minimal Python Facade Usage

```python
from mcw_core import CorePaths, LaunchRequest, MCWCore

core = MCWCore(CorePaths.from_root("./mcw-data"))
core.operations.begin()
try:
    result = core.launch(
        LaunchRequest(
            instance="My Instance",
            offline_username="Player",
            on_progress=print,
            quick_play_singleplayer="World Name",
            on_window_ready=lambda hwnd: print("Window ready:", hwnd),
        )
    )
finally:
    core.operations.finish()

print(result.minecraft_version, result.java_path)
```

The CLI can list or launch instances without the launcher GUI:

```bash
mcw-core-launch --root ./mcw-data --list
mcw-core-launch --root ./mcw-data --instance "My Instance" --username Player
```

## Public boundary

Supported consumers import from `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, or `mcw_core.api.models.*`. Modules under `src.core` and `src.models` are internal implementation details and may change outside the public compatibility contract.

## CurseForge gateway integration

MCW Core keeps CurseForge credentials outside desktop clients and supports configured HTTPS gateway endpoints. The gateway source is distributed separately and is not included in this Core source archive or wheel. Core bundles no gateway URL, client token or CurseForge API key.

Deploy the gateway separately using [mahiru7229/mcw-curseforge-gateway](https://github.com/mahiru7229/mcw-curseforge-gateway), configure its `CURSEFORGE_API_KEY`, then configure the resulting HTTPS endpoint through `MCW_CURSEFORGE_GATEWAY_URL` or the Core configuration API.

## Source layout

- `mcw_core/`: stable public API, facade, and `mcw_core.rpc` JSON-RPC 2.0 package.
- `src/core/`: Core implementation.
- `src/models/`: domain models.
- `test/`: headless Core & JSON-RPC regression suite.
- `docs/`: API, architecture, package and theme contracts.
- `examples/`: integration examples.
- `runtime/` and `mcw_core/resources/`: MCW LAN Agent.

See [RELEASE.md](RELEASE.md) and [docs/MCW_CORE_LIBRARY.md](docs/MCW_CORE_LIBRARY.md) for the release contract. Release history is in [docs/MCW_CORE_RELEASE-v1.8.0.md](docs/MCW_CORE_RELEASE-v1.8.0.md), [docs/MCW_CORE_RELEASE-v1.6.1.md](docs/MCW_CORE_RELEASE-v1.6.1.md), and [docs/MCW_CORE_RELEASE-v1.6.0.md](docs/MCW_CORE_RELEASE-v1.6.0.md).
