# MCW Core v1.2.0

MCW Core is the GUI-independent runtime distributed with MCW Launcher.

## Package

- Distribution: `mcw-core 1.2.0`
- Runtime: `mcw_core.__version__ == "1.2.0"`
- Update channel metadata: `stable`
- Python: 3.12 or newer
- Wheel: pure Python `py3-none-any`

## v1.2.0 highlights

MCW Core 1.2.0 keeps the dependency/loader hardening from v1.1.2 and adds the public-core support required by Instance Manager 2.0:

- Instance library metadata: Favorite, Group and Tags with backward-compatible `instance.json` loading.
- Public `InstanceService.set_library_metadata(...)` support.
- Public `InstanceRuntimeProfile` and runtime-profile API for Minecraft, loader and Java requirements.
- Public per-instance Java runtime selection with compatibility validation and run-lock protection.
- Unified installed-content core support used by local mod/resource-pack/shader-pack import and ownership filters.
- Retains loader-scoped dependency resolution, embedded/JarJar capability handling, safe stale managed-dependency cleanup and manual dependency pause/import/resume.
- Retains bounded modpack download concurrency, tolerant legacy `mcmod.info`, modloader installation recovery and RC storage-failure handling.

## Public API

The supported entry point is `import mcw_core`. MCW Core remains independent from PySide6/GUI code.

See `docs/MCW_CORE_LIBRARY.md`, `docs/en/CORE_GUIDE.md`, `docs/vi/CORE_GUIDE.md`, and `RELEASE-v1.2.0.md` in the source archive.
