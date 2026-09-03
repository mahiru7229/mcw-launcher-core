# Đóng gói MCW Core v1.5.0

Archive source này là bản phân phối độc lập `mcw-core 1.5.0`.

Python package gồm `mcw_core`, `src.core`, `src.models` và MCW LAN Agent đi kèm. Gói loại trừ `src.gui`, PySide6, tài khoản người dùng, cấu hình private, cache, instance, log và managed runtime.

File `mcw-curseforge-gateway-main.zip` là source gateway tùy chọn đặt cạnh Python package. Wheel không cài gateway và gateway không chứa secret triển khai hay endpoint mặc định.

Trước khi phát hành:

```bash
python -m tools.core_release_preflight
python -m pytest test -q
python -m compileall -q mcw_core src tools test examples
python -m pip wheel --no-deps --no-build-isolation .
```
