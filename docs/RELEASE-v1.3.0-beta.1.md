# MCW Core v1.3.0-beta.1

## Beta release

MCW Core **1.3.0-beta.1** is the shared-storage and cache-lifecycle foundation for MCW Launcher v1.3.0-beta.1.

### Shared immutable content

- Adds a SHA-256 content-addressed store for managed provider binaries.
- Materializes managed content with NTFS hardlinks when supported and verified copy fallback otherwise.
- Local/user-owned imports retain private copy semantics.
- Handles concurrent publication by verifying and reusing an already-published canonical blob rather than replacing it.

### Forge / NeoForge installation lifecycle

- Reuses cached Minecraft client/libraries in installer staging through verified hardlink/copy materialization.
- Publishes generated library output back to canonical shared paths.
- Removes installer staging after both successful and failed installation attempts.
- Keeps Forge and NeoForge installation logic separate.

### Provider API cache naming

- Introduces explicit API-cache names such as `CurseForgeApiCache`, `FTBApiCache`, and `ATLauncherApiCache`.
- Adds explicit `api_cache_status()` / `clear_api_cache()` client methods.
- Keeps pre-v1.3 names as compatibility aliases where needed.
- Provider API metadata remains separate from downloaded binary content and is protected from legacy storage cleanup.

### Legacy storage migration and cleanup

- Adds read-only startup probing and full reference-aware cleanup planning.
- Detects old loader staging, superseded launcher update packages, unused cached Minecraft/loader versions, unreferenced provider binary versions, stale temporary data, and orphaned shared-content blobs.
- Reports logical size, file/directory counts, and estimated physical reclaimable bytes with hardlink awareness.
- Re-scans and revalidates selected candidates immediately before deletion.
- Skips candidates whose state changed and reports removed, skipped, failed, and reclaimed totals.
- Never cleans under instance directories and explicitly protects accounts, backups, runtimes, assets, libraries, and provider API caches.

### Settings

- Settings schema v17 adds `storage.notify_legacy_cache_cleanup` with a default value of `true`.

### Package metadata

- Distribution: `mcw-core 1.3.0b1`
- Runtime: `mcw_core.__version__ == "1.3.0-beta.1"`
- Python: 3.12+
- Wheel: `py3-none-any`
