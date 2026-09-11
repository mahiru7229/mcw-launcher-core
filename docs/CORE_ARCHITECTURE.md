# Core Architecture

The core package sits between the GUI and the legacy implementation modules.
The launcher GUI should depend only on `mcw_core` and `mcw_core.api`.

## Layers

1. Public API (`mcw_core`, `mcw_core.api`)
2. Facade and orchestration (`mcw_core.facade`, `mcw_core.services`)
3. Domain and service implementations (`src.core`, `src.models` in the current launcher generation)
4. Filesystem, runtime, network, and provider integrations
