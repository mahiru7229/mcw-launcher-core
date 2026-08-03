# MCW Core 1.0.0 — Full Bilingual Developer Documentation

This documentation bundle is generated from and checked against:

- the uploaded MCW Core source repository;
- the complete MCW Launcher 1.0.0 source tree;
- the uploaded `mcw_core-1.0.0-py3-none-any.whl` distribution.

It is intended for developers who want to build another launcher, CLI, automation tool, or service on top of MCW Core without depending on the MCW Launcher GUI.

## English documentation

1. [Complete Core Guide](docs/en/CORE_GUIDE.md)
2. [API Reference](docs/en/API_REFERENCE.md)
3. [Progress, Threads, Pause and Cancel](docs/en/PROGRESS_ASYNC.md)
4. [Blueprint for Building a Launcher](docs/en/BUILD_A_LAUNCHER.md)
5. [Packaging and Release Notes](docs/en/PACKAGING_RELEASE.md)

## Tài liệu tiếng Việt

1. [Hướng dẫn Core đầy đủ](docs/vi/CORE_GUIDE.md)
2. [Tham chiếu API](docs/vi/API_REFERENCE.md)
3. [Progress, luồng, Pause và Cancel](docs/vi/PROGRESS_ASYNC.md)
4. [Bản thiết kế để xây một launcher](docs/vi/BUILD_A_LAUNCHER.md)
5. [Đóng gói và phát hành](docs/vi/PACKAGING_RELEASE.md)

## Executable examples

The `examples/` directory contains small, focused programs for:

- configuring a portable data root;
- bootstrapping the core;
- listing versions and creating instances;
- account management;
- Java scanning and installation;
- offline and account-based launch;
- progress display and cooperative pause/cancel;
- Modrinth, CurseForge and FTB workflows;
- native modpack import and portable export;
- content packs, repair, backup and diagnostics;
- a minimal PySide6 task adapter.

## Important API rule

Third-party code should import only from:

```python
import mcw_core
from mcw_core import ...
from mcw_core.api... import ...
```

Do not import `src.core`, `src.models`, `src.database`, or `src.gui` directly. The current wheel bundles compatibility implementation modules under `src`, but they are not the public contract.
