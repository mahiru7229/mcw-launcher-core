# MCW Core v1.4.0

MCW Core **1.4.0** is the stable headless runtime shipped with MCW Launcher v1.4.0.

## Highlights

- Task/cancellation-aware runtime foundations used by the v1.4 launcher lifecycle.
- Supervised Minecraft process sessions and public instance kill support.
- Strict Forge profile selection, runtime validation, and poisoned-cache recovery for legacy Forge installations.
- Adaptive Modrinth managed-file download support and one-pass multi-hash verification with bounded hash I/O.
- Update-priority-compatible operation cancellation/drain behavior.
- Diagnostics v2 data collection, issue-context generation, task/runtime/loader context, and privacy filtering.
- Retains v1.3.2 atomic-write, filesystem containment, updater-integrity and transactional package/theme safety hardening.

## Distribution metadata

- Runtime version: `1.4.0`
- Python distribution: `mcw-core 1.4.0`
- Python: `>=3.12`
- GUI dependency: none; PySide6 is not required by the standalone Core package.
