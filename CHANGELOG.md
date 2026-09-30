# Changelog

## 1.8.0 - 2026-09-30

- **100% Core & GUI Decoupling via JSON-RPC 2.0 (`mcw_core.rpc`)**:
  - Added `CoreRpcDispatcher` mapping all Core subsystems (`system.*`, `instances.*`, `java.*`, `content.*`, `catalog.*`, `worlds.*`, `screenshots.*`, `diagnostics.*`, `operations.*`) to a standardized JSON-RPC 2.0 protocol.
  - Added `StdioRpcServer` (`mcw-core-rpc --stdio`) for out-of-process Sidecar execution over `stdin`/`stdout`.
  - Added `HttpRpcServer` (`mcw-core-rpc --http`) on `127.0.0.1` with `GET /health`, `POST /rpc`, and `GET /events` (Server-Sent Events real-time stream).
  - Added `CoreRpcClient` supporting `direct`, `http`, and `stdio` sidecar transports.
- **Complete Public API & Models Re-exports (`mcw_core/api/` & `mcw_core/api/models/`)**:
  - Exported all remaining `src/core/**` modules under `mcw_core.api.*` and all `src/models/**` modules under `mcw_core.api.models.*`.
  - Added `CorePaths.instances_root` helper property.
- **Merged `1.7.0` – `1.7.1.1` Hotfix Engine & Hardware GPU Caching**:
  - Added `HotfixManager` and `HotfixMetaPathFinder` (`mcw_core.api.update.hotfix_manager`) for SHA-256 verified runtime patching from Cloudflare Edge CDN (`mcw-download.pages.dev`) with atomic directory swaps and automatic cleanup on upgrade.
  - Added persistent hardware GPU detection caching in `GpuPreferenceManager` (`mcw_core.api.hardware.gpu_preference_manager`).

## 1.6.1 - 2026-09-23

- Modloader metadata retries: Added `HttpDownloader.get_with_retry` with at least 5 attempts and exponential backoff for Forge, NeoForge, Fabric, and Quilt metadata clients to survive transient network issues.
- Extended Windows path support: `copy_file`, `link_file`, `same_file` in `windows_path.py` with `\\?\` prefix to handle paths exceeding 260 characters (`MAX_PATH`).
- Added chunked streaming fallback in `copy_file` when low-level Win32 copy APIs fail.
- Shortened temporary publishing artifact filenames in `SharedFileMaterializer` (`.tmp_<hex>.pub`).
- Protected `NeoForgeVersionManager` and `ForgeVersionManager` against long paths during library extraction and caching (fixes #32).

## 1.6.1-beta.1 - 2026-09-23

- Extended Windows path support: `copy_file`, `link_file`, `same_file` in `windows_path.py` with `\\?\` prefix to handle paths exceeding 260 characters (`MAX_PATH`).
- Added chunked streaming fallback in `copy_file` when low-level Win32 copy APIs fail.
- Shortened temporary publishing artifact filenames in `SharedFileMaterializer` (`.tmp_<hex>.pub`).
- Protected `NeoForgeVersionManager` and `ForgeVersionManager` against long paths during library extraction and caching (fixes #32).

## 1.6.0 - 2026-09-20

- Promoted to stable release aligned with MCW Launcher v1.6.0.
- CurseForge mod loader normalization: strips game-version prefixes, fixes duplicated Maven URL 404s, extended loader aliases.
- Flexible `modLoaders` parsing in CurseForge manifest (list-of-dicts, list-of-strings, single-object).
- ATLauncher Forge version normalization and auto-healing of existing instances with redundant prefixes.
- ATLauncher: server-only file actions skipped; standard Forge launch wrappers recognized.
- FTB run-lock protection: timeout extended to 600 s with periodic heartbeat; lock auto-recreated if evicted while game runs.
- Update services: automatic cleanup of legacy onedir `_internal/` during upgrades to one-file builds.
- New public API modules: `mclogs_client`, `integrations.discord`, `java.jvm_presets`, `minecraft.screenshot_manager`, `minecraft.world_manager`.

## 1.5.1 - 2026-09-11

- Added Fabric `provides` alias support, including nested JAR capability indexing.
- Fixed dependency resolution for aliases such as `cloth-config2`.
- Added verified discovery of undeclared Modrinth dependencies for managed modpacks.
- Added provider alias caching and clearer grouped dependency diagnostics.
- Aligned update services with MCW Launcher v1.5.1, including schema-2 packages, bundled updater handoff, emergency Bridge support and hardened Windows replacement/rollback.
- Continued to distribute the CurseForge gateway separately from MCW Core.

## 1.5.0 - 2026-09-03

- Promoted the Core runtime validated by MCW Launcher v1.5.0 Beta 4 to Stable.
- Added Linux XDG storage, Secret Service credentials, managed Java and process-group supervision.
- Added Linux automatic update support with package verification, backup, rollback and restart.
- Added Forge/NeoForge Linux support and Java-version inference for incomplete loader metadata.
- Added resumable compatibility confirmation so dependency resolving/checking is not repeated.
- Expanded the public facade for platform migration, OptiFine, content management and update services.
- Kept CurseForge gateway configuration opt-in; no endpoint, token or API key is bundled.
