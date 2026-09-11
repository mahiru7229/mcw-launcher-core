# Packaging MCW Core v1.5.1

This source archive is the standalone `mcw-core 1.5.1` distribution.

The Python package includes `mcw_core`, `src.core`, `src.models` and the bundled MCW LAN Agent. It excludes `src.gui`, PySide6, user accounts, private configuration, caches, instances, logs and managed runtimes.

The CurseForge gateway source archive is distributed separately and is intentionally not included in this Core source archive or wheel. MCW Core contains the gateway client/configuration integration but no deployment secret or default endpoint.

Before publishing:

```bash
python -m tools.core_release_preflight
python -m pytest test -q
python -m compileall -q mcw_core src tools test examples
python -m pip wheel --no-deps --no-build-isolation .
```
