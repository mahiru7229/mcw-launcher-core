# MCW Core v1.6.0

MCW Core `1.6.0` is the Stable headless runtime shipped with MCW Launcher `v1.6.0`.

## Highlights

- Update services aligned with Launcher 1.6.0: one-file packaging, automatic legacy onedir `_internal/` scrubbing during upgrades.
- CurseForge mod loader normalization: strips game-version prefixes from loader version IDs, fixes duplicated Maven URL prefixes causing 404 errors.
- Extended `LOADER_ALIASES` covering `forge`, `minecraftforge`, `fabric`, `fabric-loader`, `quilt`, `quilt-loader`, `neoforge`, `neoforged`, `neo`.
- Flexible `modLoaders` parsing: supports list-of-dicts, list-of-strings, and single-object `modLoader` structures in CurseForge manifest.
- ATLauncher Forge version normalization: strips redundant game-version prefix from loader version strings; auto-heals existing instances.
- ATLauncher: skips server-only file actions and recognizes standard Forge launch wrappers during unsupported-actions validation.
- FTB run-lock protection: timeout extended to 600 s, periodic heartbeat touch during content checks, automatic lock file recreation if evicted while game is running.
- New public API modules: `mcw_core.api.diagnostics.mclogs_client`, `mcw_core.api.integrations.discord`, `mcw_core.api.java.jvm_presets`, `mcw_core.api.minecraft.screenshot_manager`, `mcw_core.api.minecraft.world_manager`.
- Windows x64 and Linux x64 runtime abstractions, XDG storage and safe legacy migration remain supported.
- Vanilla, Fabric, Quilt, Forge and NeoForge instance pipelines remain supported.
- Microsoft authentication, managed Java, Modrinth, CurseForge, FTB and ATLauncher integrations remain available.

## Distribution contract

- Distribution: `mcw-core 1.6.0`
- Runtime: `mcw_core.__version__ == "1.6.0"`
- Python: `>=3.12`
- GUI dependency: none
- Public imports: `mcw_core` and `mcw_core.api.*`
- Bundled LAN Agent: included
- CurseForge gateway source archive: not bundled with MCW Core

The gateway is distributed/deployed separately. A deployment must supply its own `CURSEFORGE_API_KEY` and the Core must be configured with the resulting HTTPS URL.
