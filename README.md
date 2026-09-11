# MCW Core 1.5.1

MCW Core is the headless runtime shipped with MCW Launcher `v1.5.1`. This source distribution contains the complete public API, implementation, data models, tests, documentation, examples and LAN Agent resource. The separate CurseForge gateway source archive is intentionally not bundled with MCW Core.

PySide6 and the launcher GUI are intentionally not part of the Core distribution.

## What changed in 1.5.1

- Added Fabric `provides` alias support so dependency IDs such as `cloth-config2` resolve correctly.
- Added verified recovery for undeclared Modrinth dependencies in managed modpacks.
- Improved dependency error grouping and provider alias caching.
- Aligned update services with Launcher 1.5.1: schema-2 package validation, bundled updater handoff, emergency Bridge strategy and hardened Windows executable replacement.
- Kept the CurseForge gateway source separate from the Core distribution.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest test -q
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Minimal usage

```python
from mcw_core import CorePaths, LaunchRequest, MCWCore

core = MCWCore(CorePaths.from_root("./mcw-data"))
core.operations.begin()
try:
    result = core.launch(
        LaunchRequest(
            instance="My Instance",
            offline_username="Player",
            on_progress=print,
        )
    )
finally:
    core.operations.finish()

print(result.minecraft_version, result.java_path)
```

The CLI can list or launch instances without the launcher GUI:

```bash
mcw-core-launch --root ./mcw-data --list
mcw-core-launch --root ./mcw-data --instance "My Instance" --username Player
```

## Public boundary

Supported consumers import from `mcw_core` or `mcw_core.api.*`. Modules under `src.core` and `src.models` are implementation details and may change outside the public compatibility contract.

## CurseForge gateway integration

MCW Core keeps CurseForge credentials outside desktop clients and supports configured HTTPS gateway endpoints. The gateway source is distributed separately and is not included in this Core source archive or wheel. Core bundles no gateway URL, client token or CurseForge API key.

Deploy the gateway separately, configure its `CURSEFORGE_API_KEY`, then configure the resulting HTTPS endpoint through `MCW_CURSEFORGE_GATEWAY_URL` or the Core configuration API.

## Source layout

- `mcw_core/`: stable public API and facade.
- `src/core/`: Core implementation.
- `src/models/`: domain models.
- `test/`: headless Core regression suite.
- `docs/`: API, architecture, package and theme contracts.
- `examples/`: integration examples.
- `runtime/` and `mcw_core/resources/`: MCW LAN Agent.

See [RELEASE.md](RELEASE.md) and [docs/MCW_CORE_LIBRARY.md](docs/MCW_CORE_LIBRARY.md) for the release contract.
