# MCW Core v1.5.0 release notes

This is the standalone source release of the same Core runtime bundled with MCW Launcher `v1.5.0`.

The archive contains the full headless implementation, public facade, models, tests, examples, documentation, theme contracts, language packs, LAN Agent and the optional CurseForge gateway source ZIP. It deliberately excludes the PySide6 GUI, user accounts, private configuration, downloaded game data, caches, logs and managed Java runtimes.

The public compatibility boundary is `mcw_core` and `mcw_core.api.*`. Direct imports from `src.core` or `src.models` are unsupported implementation access.
