# Packaging MCW Core v1.5.0

This source archive is the standalone `mcw-core 1.5.0` distribution.

The Python package includes `mcw_core`, `src.core`, `src.models` and the bundled MCW LAN Agent. It excludes `src.gui`, PySide6, user accounts, private configuration, caches, instances, logs and managed runtimes.

The optional `mcw-curseforge-gateway-main.zip` is distributed beside the Python package as source material. It is not installed by the wheel and contains no deployment secret or default endpoint.

Before publishing:

```bash
python -m tools.core_release_preflight
python -m pytest test -q
python -m compileall -q mcw_core src tools test examples
python -m pip wheel --no-deps --no-build-isolation .
```
