# Migration Notes

## From launcher-internal imports

Prefer:

```python
from mcw_core.api.instance.instance_manager import InstanceManager
```

instead of importing internal GUI or `src.gui` modules.

## Stability promise

The 1.0.0 core release establishes the first stable public namespace.
Internal implementation details may still evolve behind the API boundary.
