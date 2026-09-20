# MCW Core v1.6.0 release notes

This is the standalone source release of the Core runtime bundled with MCW Launcher `v1.6.0`.

## Changes from 1.5.1

### Public API additions

- **`LaunchRequest`** — three new optional fields:
  - `quick_play_singleplayer: str = ""` — world name passed to the Java Edition Quick Play argument.
  - `quick_play_multiplayer: str = ""` — `host:port` string to connect to a server on startup.
  - `on_window_ready: Callable[[int], None] | None = None` — callback invoked with the native window handle once the game window is visible.

- **`InstanceCreateRequest`** — one new optional field:
  - `jvm_arguments: tuple[str, ...] = ()` — extra JVM flags written to the new instance's `settings.json` on creation.

- **New public API modules**:
  - `mcw_core.api.integrations` (package) — Discord Rich Presence bridge via `discord.py`.
  - `mcw_core.api.diagnostics.mclogs_client` — MCLogs.app log upload client.
  - `mcw_core.api.java.jvm_presets` — built-in JVM argument preset helpers.
  - `mcw_core.api.minecraft.screenshot_manager` — screenshot folder and file management.
  - `mcw_core.api.minecraft.world_manager` — world save enumeration and management.

### CurseForge modpack improvements

- Loader version normalization: strips redundant game-version prefix (e.g. `1.20.1-47.3.0` → `47.3.0`) before constructing Maven download URLs, eliminating 404 errors on affected packs.
- Extended loader aliases: `minecraftforge`, `fabric-loader`, `quilt-loader`, `neoforged`, `neo` are now all recognized.
- Flexible `modLoaders` parsing: handles list-of-dicts, list-of-strings, and single-object `modLoader` structures in `manifest.json`.
- `sortableGameVersions` is consulted alongside `gameVersions` when extracting loader info from CurseForge file metadata.

### ATLauncher improvements

- Forge version normalization: strips redundant `<game_version>-<game_version>-<forge_version>` prefix.
- Auto-healing: on next launch, existing ATLauncher instances with the malformed prefix in `instance.json` are corrected automatically.
- Server-only file actions (e.g. `SF4 Server Configs`) are skipped during the unsupported-actions safety check.
- Standard Forge launch wrapper classes and tweaker arguments are recognized and no longer block installation.

### FTB run-lock improvements

- `PREPARING_LOCK_TIMEOUT_SECONDS` increased from 120 s to 600 s.
- Heartbeat `touch()` called every 50 files and before each download batch so the lock never expires during large content verification passes.
- If the lock file is deleted while Minecraft is running, it is automatically recreated with the correct `running` state and PID, keeping the launcher UI accurate.

### Update system improvements

- `UpdateApplier._cleanup_legacy_onedir()` removes the `_internal/` directory from the installation target when the incoming package does not ship `_internal/` (i.e. when upgrading from a onedir beta to a onefile stable build).
- Empty directory trees left over after stale-file removal are pruned automatically.
- `cleanup_paths` in `mcw-update.json` now includes `_internal` for onefile packages.

The CurseForge gateway source remains a separate project and is not bundled in this archive or wheel.
