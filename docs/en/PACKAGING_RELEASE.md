# Packaging and Releasing MCW Core 1.0.1

## Audit findings from the supplied artifacts

1. Wheel metadata declares 1.0.0.
2. The uploaded wheel contains `src/config.py` reporting `1.0.0-rc.1`, so `mcw_core.__version__` can disagree with package metadata.
3. The reduced core repository packages only `mcw_core*`, while the facade currently imports implementation classes from `src`.
4. The complete launcher source uses a compatibility wheel configuration that includes core/model/database implementation packages and excludes the GUI.

Synchronize runtime and distribution versions before publishing.

## Compatibility package configuration

For the first stable release, include `mcw_core*`, `src`, `src.core*`, `src.models*` and `src.database*`, while excluding `src.gui*` and tests. A future internal refactor should move implementation under a private `mcw_core` namespace before removing `src` from the wheel.

## Build and verify

```powershell
python -m pip install build wheel
python -m build
```

Install the wheel in a clean Python 3.12 environment, verify `mcw_core.__version__ == "1.0.0"`, verify import without PySide6, test the CLI, bundled LAN agent, public API tests and all examples.

## Stability levels

- `mcw_core`: stable facade;
- `mcw_core.api.*`: public granular boundary;
- `src.*`: compatibility implementation, not a consumer contract.
