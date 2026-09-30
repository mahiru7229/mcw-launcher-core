# MCW Core v1.8.0 release notes

This is the standalone source and wheel release of the Core runtime bundled with MCW Launcher `v1.8.0`.

## Changes from 1.6.1 / 1.7.1

### 1. 100% Core & GUI Decoupling via JSON-RPC 2.0 (`mcw_core.rpc`)

- Added `mcw_core.rpc` package providing a complete, language-agnostic **JSON-RPC 2.0** interface:
  - `CoreRpcDispatcher`: Routes `system.*`, `instances.*`, `java.*`, `content.*`, `catalog.*`, `worlds.*`, `screenshots.*`, `diagnostics.*`, and `operations.*` commands and broadcasts `RpcEvent` notifications.
  - `StdioRpcServer` (`mcw-core-rpc --stdio`): Runs MCW Core as an isolated Sidecar process communicating over line-delimited `stdin`/`stdout` JSON-RPC 2.0.
  - `HttpRpcServer` (`mcw-core-rpc --http`): Runs a localhost HTTP daemon (`127.0.0.1`) with `GET /health`, `POST /rpc`, and real-time `GET /events` (Server-Sent Events).
  - `CoreRpcClient`: Multi-transport client supporting `mode="direct"`, `mode="http"`, and `mode="stdio"`.

### 2. Complete Public API & Models Boundary (`mcw_core/api/` & `mcw_core/api/models/`)

- Exported all Core services under `mcw_core.api.*` and all domain models under `mcw_core.api.models.*`.
- GUI frontends and external consumers have zero dependency on `src.core.*` or `src.models.*`.

### 3. Dynamic Hotfix Engine & Hardware GPU Caching (`1.7.0` – `1.7.1.1`)

- Added `HotfixManager` and `HotfixMetaPathFinder` (`mcw_core.api.update.hotfix_manager`) for SHA-256 verified runtime patching from Cloudflare Edge CDN (`mcw-download.pages.dev`) with atomic directory swaps and automatic cleanup on upgrade (`clean_on_upgrade`).
- Added persistent hardware GPU detection caching in `GpuPreferenceManager` (`mcw_core.api.hardware.gpu_preference_manager`).

### Distribution & Installation

- Prebuilt `.whl` distribution package `mcw_core-1.8.0-py3-none-any.whl` available for standalone headless consumers and GUI frontends.
- Tested and verified across Windows and Linux CI (`python -m pytest test -v`).
