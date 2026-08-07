# MCW Core v1.1.2

MCW Core is the GUI-independent runtime distributed with MCW Launcher.

## Package

- Distribution: `mcw-core 1.1.2`
- Runtime: `mcw_core.__version__ == "1.1.2"`
- Update channel metadata: `stable`
- Python: 3.12 or newer
- Wheel: pure Python `py3-none-any`

## v1.1.2 highlights

MCW Core 1.1.2 synchronizes the complete core changes validated through the MCW Launcher v1.1.2 beta line:

- Loader-scoped dependency parsing and environment-capability handling.
- Pack-manifest authority for curated modpacks without foreign-loader false blockers.
- Embedded/JarJar capability resolution, including nested dependencies such as `expandability`.
- Correct primary-mod duplicate detection, safer stale managed-dependency cleanup, and improved Forge/Maven version matching.
- Faster CurseForge modpack downloads and reduced dependency-progress event pressure.
- Faster and more resilient Fabric, Quilt, Forge, and NeoForge installation paths.
- Tolerant legacy `mcmod.info` parsing for salvageable metadata.
- Same-session manual CurseForge/Modrinth dependency recovery with pause/import/resume semantics.
- Manual import remains protected by the active instance preparing-lock token and still honors cancellation.

## Public API

The supported entry point is `import mcw_core`. Existing public contracts from v1.1.1 remain available. v1.1.2 extends launch requests with manual-content recovery support while retaining GUI-independent core behavior.

See `docs/MCW_CORE_LIBRARY.md`, `docs/en/CORE_GUIDE.md`, `docs/vi/CORE_GUIDE.md`, and `RELEASE-v1.1.2.md` in the source archive.
