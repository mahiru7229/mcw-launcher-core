# MCW Core 1.1.0

MCW Core is the GUI-independent runtime used by **MCW Launcher v1.1.0**. It provides the public Python API for instances, Java selection, Minecraft launch, mod loaders, provider downloads, repair, backup, process supervision, and package workflows.

## Install

```bash
python -m pip install mcw_core-1.1.0-py3-none-any.whl
```

Verify:

```bash
python -c "import mcw_core; print(mcw_core.__version__)"
```

Expected output:

```text
1.1.0
```

## v1.1.0 highlights

- Automatic or custom Java selection with compatibility recovery.
- The Forge/NeoForge installer uses the instance Java choice.
- Legacy Forge support for singleton launch arguments, LaunchWrapper libraries, native classifiers, OS rules, and old certificate validation behavior.
- Bounded provider/metadata recovery used by the launcher.
- CurseForge manual-download links prefer stable slug-based file pages instead of failed CDN URLs or numeric project placeholders.
- Public CurseForge URL helpers are exposed through `mcw_core.api.curseforge.curseforge_links`.

## Compatibility

- Existing imports from `mcw_core` and `mcw_core.api.*` remain supported.
- No existing public class, method, field, or exception is intentionally removed or renamed.
- Applications should import public contracts from `mcw_core` rather than implementation modules under `src.core`.
- The default CurseForge gateway remains empty; deployments must provide their own configured gateway.

## Minimal example

```python
from mcw_core import CorePaths, LaunchRequest, MCWCore

core = MCWCore(CorePaths.from_root(r"D:\\Games\\MCW"))
result = core.launch(
    LaunchRequest(
        instance="My Instance",
        offline_username="Player",
        on_progress=print,
    )
)
print(result.minecraft_version, result.java_path)
```

## Tiếng Việt

MCW Core 1.1.0 là runtime headless đi kèm MCW Launcher v1.1.0. Bản này đồng bộ toàn bộ sửa lỗi Java, Forge legacy, CurseForge và pipeline launch của nhánh 1.1. Public API cũ vẫn được giữ tương thích; ứng dụng bên ngoài nên import từ `mcw_core` hoặc `mcw_core.api.*`.

Xem thêm:

- [`docs/MCW_CORE_LIBRARY.md`](docs/MCW_CORE_LIBRARY.md)
- [`docs/RELEASE-v1.1.0.md`](docs/RELEASE-v1.1.0.md)
