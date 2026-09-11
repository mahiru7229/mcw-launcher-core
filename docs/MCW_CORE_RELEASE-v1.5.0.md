# MCW Core v1.5.0 release notes

This is the standalone source release of the same Core runtime bundled with MCW Launcher `v1.5.0`.

The archive contains the full headless implementation, public facade, models, tests, examples, documentation, theme contracts, language packs and LAN Agent. It deliberately excludes the PySide6 GUI, user accounts, private configuration, downloaded game data, caches, logs, managed Java runtimes and the separately distributed CurseForge gateway source archive.

The public compatibility boundary is `mcw_core` and `mcw_core.api.*`. Direct imports from `src.core` or `src.models` are unsupported implementation access.
