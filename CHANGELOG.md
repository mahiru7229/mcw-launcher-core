# Changelog

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
