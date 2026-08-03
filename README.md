# MCW Core 1.0.0

MCW Core is the headless runtime and service layer that powers MCW Launcher.
It exposes a stable Python API for instance management, Java discovery,
Minecraft launch orchestration, modpack workflows, backup/repair utilities,
and content management without requiring the PySide6 GUI.

## Highlights in 1.0.0

- Stable public API surface under `mcw_core` and `mcw_core.api`.
- Headless launch flow with progress callbacks.
- Instance creation, loading, cloning, deletion, and status management.
- Java scanning and installation helpers.
- Modrinth, CurseForge, FTB, and portable package support through the public API.
- Backup, repair, diagnostics, and security helpers.
- LAN hosting helpers and managed content utilities.

## Install

```bash
pip install mcw-core==1.0.0
```

## Quick example

```python
from mcw_core import get_default_core, LaunchRequest
from mcw_core.api.instance.instance_manager import InstanceManager

core = get_default_core()
instance = InstanceManager.load('My Instance')
request = LaunchRequest(instance=instance, account=None, authentication=None)

result = core.launch(request)
print(result)
```

## Repository layout

- `mcw_core/` — public package.
- `docs/` — usage guides and release notes.
- `LICENSE` — MIT license.

## Documentation

- `docs/QUICKSTART.md`
- `docs/API_OVERVIEW.md`
- `docs/USAGE.md`
- `docs/MIGRATION.md`
- `docs/CORE_ARCHITECTURE.md`
- `docs/RELEASE-v1.0.0.md`

## Notes

This source bundle is intended for the public core repository snapshot.
The runtime compatibility wheel used for the first 1.0.0 release may still bundle
supporting compatibility modules required by the current launcher generation.
