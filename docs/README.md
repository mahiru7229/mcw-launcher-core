# MCW Core v1.5.0 Documentation

This directory is the documentation hub for the stable **MCW Core 1.5.0** distribution.
The supported public boundary is `mcw_core` and `mcw_core.api.*`; `src.core` and
`src.models` remain implementation details.

## Start here

- **Vietnamese complete guide:** [vi/MCW_CORE_V1_5_COMPLETE_GUIDE.md](vi/MCW_CORE_V1_5_COMPLETE_GUIDE.md)
- **English core guide:** [en/CORE_GUIDE.md](en/CORE_GUIDE.md)
- **Quick start:** [QUICKSTART.md](QUICKSTART.md)
- **Build a launcher:** [vi/BUILD_A_LAUNCHER.md](vi/BUILD_A_LAUNCHER.md) / [en/BUILD_A_LAUNCHER.md](en/BUILD_A_LAUNCHER.md)
- **Public API overview:** [API_OVERVIEW.md](API_OVERVIEW.md)
- **Full API reference:** [vi/API_REFERENCE.md](vi/API_REFERENCE.md) / [en/API_REFERENCE.md](en/API_REFERENCE.md)
- **Architecture:** [CORE_ARCHITECTURE.md](CORE_ARCHITECTURE.md)
- **Troubleshooting:** [vi/TROUBLESHOOTING.md](vi/TROUBLESHOOTING.md)

## Functional guides

| Area | Documentation |
|---|---|
| Instances | [INSTANCE_SYSTEM.md](INSTANCE_SYSTEM.md) |
| Packages / portable content | [PACKAGE_FORMAT.md](PACKAGE_FORMAT.md) |
| Modrinth | [MODRINTH_INTEGRATION.md](MODRINTH_INTEGRATION.md), [FORGE_MODRINTH.md](FORGE_MODRINTH.md) |
| CurseForge | [FORGE_CURSEFORGE.md](FORGE_CURSEFORGE.md) |
| Updates | [UPDATE_PACKAGES.md](UPDATE_PACKAGES.md) |
| Language packs | [LANGUAGE_PACKS.md](LANGUAGE_PACKS.md) |
| Themes | [THEME_CREATION_GUIDE.md](THEME_CREATION_GUIDE.md), [THEME_RUNTIME_CONTRACT.md](THEME_RUNTIME_CONTRACT.md) |
| Theme assets | [THEME_ASSET_GUIDE.md](THEME_ASSET_GUIDE.md) |
| Theme animation | [THEME_ANIMATION_GUIDE.md](THEME_ANIMATION_GUIDE.md) |
| Theme fonts | [THEME_FONT_GUIDE.md](THEME_FONT_GUIDE.md) |
| Theme motion | [THEME_MOTION_GUIDE.md](THEME_MOTION_GUIDE.md) |
| Migration | [MIGRATION.md](MIGRATION.md) |
| Packaging / release | [vi/PACKAGING_RELEASE.md](vi/PACKAGING_RELEASE.md) / [en/PACKAGING_RELEASE.md](en/PACKAGING_RELEASE.md) |
| Async / progress | [vi/PROGRESS_ASYNC.md](vi/PROGRESS_ASYNC.md) / [en/PROGRESS_ASYNC.md](en/PROGRESS_ASYNC.md) |

## v1.5.0 platform and provider coverage

MCW Core v1.5.0 includes public modules for:

- Windows x64 and Linux x64 storage/runtime/update integration.
- Vanilla, Fabric, Quilt, Forge and NeoForge instance pipelines.
- Managed Java provisioning and Java compatibility policy.
- Offline and Microsoft account flows.
- Modrinth, CurseForge, FTB and ATLauncher providers.
- OptiFine inspection/install/repair/uninstall.
- Content library, portable content and modpack package workflows.
- Backup, repair, diagnostics and issue-report generation.
- Process supervision, instance run locks and startup recovery.
- Shared content storage and legacy storage cleanup/migration.
- Theme, animation, font, motion and language runtime contracts.

The generated API references include every non-`__init__` module under
`mcw_core/api/` in this source distribution. See [API_COVERAGE.json](API_COVERAGE.json)
for the source-derived coverage snapshot.
