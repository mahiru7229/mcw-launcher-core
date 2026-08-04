# MCW Core 1.0.1

MCW Core is the headless runtime and service layer used by MCW Launcher. It provides a public Python API for building a Minecraft launcher without depending on the PySide6 GUI.

## Install

```bash
python -m pip install mcw_core-1.0.1-py3-none-any.whl
```

Verify the release:

```bash
python -c "import mcw_core; print(mcw_core.__version__)"
```

Expected output:

```text
1.0.1
```

## Public API boundary

External applications should import only from:

```python
import mcw_core
from mcw_core.api.instance.instance_manager import InstanceManager
```

The bundled `src.*` packages are compatibility implementation details for the 1.0.x generation. They are shipped so the wheel is runnable, but they are not the stable API contract.

## Quick launch example

```python
from mcw_core import LaunchRequest, ProgressEvent, get_default_core


def on_progress(event: ProgressEvent) -> None:
    percentage = "" if event.percentage is None else f" {event.percentage:.1f}%"
    print(f"[{event.stage.value}]{percentage} {event.message}")


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

`launch()` returns after the Minecraft process starts. Use `LaunchRequest.on_exit` to receive the final game exit result.

## 1.0.1 highlights

- Correct resource/shader pack roots and safe v1.0.0 migration.
- Safe add-while-running policy for non-destructive content installation.
- Newest-first FTB versions.
- First-run Java/RAM recommendation service.
- Ask/Block/Allow/Inherit compatibility policy and one-time confirmation retry.
- Provider artwork fallback for imported modpacks.
- Theme text-palette and contrast helpers.

## Documentation

### English

- [`docs/en/CORE_GUIDE.md`](docs/en/CORE_GUIDE.md)
- [`docs/en/API_REFERENCE.md`](docs/en/API_REFERENCE.md)
- [`docs/en/PROGRESS_ASYNC.md`](docs/en/PROGRESS_ASYNC.md)
- [`docs/en/BUILD_A_LAUNCHER.md`](docs/en/BUILD_A_LAUNCHER.md)
- [`docs/en/V1_0_1_API_ADDITIONS.md`](docs/en/V1_0_1_API_ADDITIONS.md)

### Tiếng Việt

- [`docs/vi/CORE_GUIDE.md`](docs/vi/CORE_GUIDE.md)
- [`docs/vi/API_REFERENCE.md`](docs/vi/API_REFERENCE.md)
- [`docs/vi/PROGRESS_ASYNC.md`](docs/vi/PROGRESS_ASYNC.md)
- [`docs/vi/BUILD_A_LAUNCHER.md`](docs/vi/BUILD_A_LAUNCHER.md)
- [`docs/vi/V1_0_1_API_ADDITIONS.md`](docs/vi/V1_0_1_API_ADDITIONS.md)

---

# MCW Core 1.0.1 — Tiếng Việt

MCW Core là lớp runtime và service headless đứng sau MCW Launcher. Thư viện cung cấp public API Python để xây một Minecraft launcher mà không phụ thuộc vào giao diện PySide6.

## Nguyên tắc import

Ứng dụng bên ngoài chỉ nên import từ `mcw_core` hoặc `mcw_core.api.*`. Các module `src.*` được đóng gói để tương thích với implementation 1.0.x, nhưng không phải public API ổn định.

## Điểm mới trong 1.0.1

- Sửa đúng đường dẫn resource pack/shader pack và migration dữ liệu 1.0.0.
- Cho phép thêm gói tài nguyên mới khi game đang chạy nhưng chặn thao tác phá hủy.
- Sắp xếp FTB mới nhất trước.
- Service gợi ý Java/RAM cho First Run Setup.
- Chính sách tương thích Hỏi/Chặn/Cho phép/Kế thừa và retry một lần có xác nhận.
- Lấy icon provider theo cơ chế best-effort khi import modpack.
- Helper màu chữ và kiểm tra độ tương phản cho theme.

Xem [`docs/RELEASE-v1.0.1.md`](docs/RELEASE-v1.0.1.md) để đọc release notes đầy đủ.
