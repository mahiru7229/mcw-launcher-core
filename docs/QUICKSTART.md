# Quickstart

## Chạy giao diện

Từ virtual environment đã cài `-e '.[dev,build]'`:

```bash
python launcher.py
```

## Dùng public core facade

```python
from pathlib import Path

from mcw_core import CorePaths, MCWCore

core = MCWCore(CorePaths.from_root(Path("./mcw-data")))
for instance in core.instances.list():
    print(instance.name, instance.version_id)
```

## Launch offline với progress

```python
from mcw_core import LaunchRequest, get_default_core


def on_progress(event):
    print(event.stage, event.message, event.percentage)


core = get_default_core()
result = core.launch(
    LaunchRequest(
        instance="My Instance",
        offline_username="Player",
        on_progress=on_progress,
    )
)
print(result.minecraft_version, result.java_path)
```

Tên instance phải tồn tại. Để dùng tài khoản Microsoft, truyền cặp `account` và `authentication` đã được public authentication API tạo ra thay cho `offline_username`.

Xem thêm [MCW Core library](MCW_CORE_LIBRARY.md) và [API overview](API_OVERVIEW.md).
