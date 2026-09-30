# MCW Core v1.8.0

MCW Core `1.8.0` is the Stable headless runtime and JSON-RPC 2.0 server shipped with MCW Launcher `v1.8.0`.

## Highlights

- **100% Core & GUI Decoupling via JSON-RPC 2.0 (`mcw_core.rpc`)**:
  - `CoreRpcDispatcher`: Headless JSON-RPC 2.0 command & event router (`system.*`, `instances.*`, `java.*`, `content.*`, `catalog.*`, `worlds.*`, `screenshots.*`, `diagnostics.*`, `operations.*`).
  - `StdioRpcServer` (`mcw-core-rpc --stdio`): Line-delimited JSON-RPC 2.0 over `stdin`/`stdout` for Sidecar architectures (Tauri v2, TypeScript/React, C#, CLI).
  - `HttpRpcServer` (`mcw-core-rpc --http`): Localhost HTTP + Server-Sent Events (SSE) daemon (`127.0.0.1`) with `/health`, `/rpc`, and `/events`.
  - `CoreRpcClient`: Multi-transport Python client supporting `direct`, `http`, and `stdio` sidecar modes.
- **Complete Public API & Models Boundary**:
  - 100% of Core services and domain models are exposed under `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, and `mcw_core.api.models.*`.
- **Dynamic Hotfix Engine & Hardware GPU Caching (`1.7.x` – `1.8.0`)**:
  - `HotfixManager` and `HotfixMetaPathFinder` with SHA-256 verification, atomic directory swaps, and automatic cleanup on upgrade.
  - Persistent GPU hardware detection caching in `GpuPreferenceManager`.
- **Extended Windows Path Support (`\\?\`) & Modloader Metadata Retries**:
  - Full `\\?\` extended path support on Windows (`MAX_PATH` > 260 chars) and 5-attempt exponential backoff retries across all Modloader metadata clients.

## Distribution contract

- Distribution: `mcw-core 1.8.0` (`mcw_core-1.8.0-py3-none-any.whl`)
- Runtime: `mcw_core.__version__ == "1.8.0"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core`, `mcw_core.rpc`, `mcw_core.api.*`, and `mcw_core.api.models.*`
- CLI entrypoints: `mcw-core-launch` and `mcw-core-rpc`
- Bundled LAN Agent: included
- CurseForge gateway source archive: not bundled with MCW Core

The gateway is distributed/deployed separately. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
