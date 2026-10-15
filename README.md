# MCW Core 1.8.2-beta.1

MCW Core is the headless engine runtime shipped with MCW Launcher `v1.8.2-beta.1`. This source distribution contains the complete public API, JSON-RPC 2.0 server (`mcw_core.rpc`), implementation, data models, tests, documentation, examples, and LAN Agent resource. The separate CurseForge gateway source archive is intentionally not bundled with MCW Core.

PySide6 and the launcher GUI are intentionally not part of the Core distribution.

## What changed in 1.8.2-beta.1

- **Extended MCW LAN Agent Support to Lower Minecraft Versions (Down to 1.14+)**:
  - `LanAgentTargetResolver` extended from 1.17+ to 1.14.0+ (supports Minecraft 1.14, 1.15, 1.16.5+).
  - Automatically identifies Forge SRG (`func_71229_d`), Fabric Intermediary (`method_3864`/`method_3782`), and Mojang official mapping targets to eliminate "Invalid session" disconnects when playing over offline LAN.
- **Hotfix Manager Pre-bootstrap Auto-Sync & Memory Eviction**:
  - Added fast fail-open auto-sync (`auto_sync=True`, timeout 2.0s) for newly downloaded or unpatched installations before UI modules are cached in RAM.
  - Automatically evicts stale in-memory modules (`sys.modules`) upon applying patches, paired with observer notification callbacks.
- **Offline Account Steve / Alex Default Models Without Online Skin Lookups**:
  - Offline accounts automatically determine Steve (`classic`) or Alex (`slim`) models locally using Minecraft's official `DefaultPlayerSkin` UUID hash algorithm (`OfflineAuthentication.default_skin_variant`).
  - Completely bypasses external skin network calls (Minotar/Mojang), preventing accidental skin leakage even when an offline username matches a licensed player.

## What changed in 1.8.1

- **Direct CurseForge Countdown Download URL Resolution & Slug Resolver**:
  - Added direct countdown URL generator `resolve_download_page_url` (`https://www.curseforge.com/minecraft/{category}/{slug}/download/{file_id}`) in `CurseForgeLinks`.
  - Added slug resolution via fallback service `cflookup.com/{project_id}` and in-memory cache when project slug is unknown without an API key.
- **Maven Library Deduplication on Classpath**:
  - Implemented version-aware deduplication in `ClasspathBuilder` (`deduplicate_maven_libraries`), keeping the latest version of libraries (e.g. Log4j 2.15.0+, lwjgl) while preserving classpath order.
- **Prism Launcher Direct Launch Execution**:
  - Aligned preflight checks with Prism Launcher behavior: non-blocking mod dependency resolution warnings delegating final checks to the ModLoader runtime.
- **Hotfix Manager & Mod Manager Enhancements**:
  - Hardened runtime hotfix reload and multi-mod manual installation pipeline.

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

## Installation

### From prebuilt Wheel (`.whl`)

```bash
pip install mcw_core-1.8.2b1-py3-none-any.whl
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
