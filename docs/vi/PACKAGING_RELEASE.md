# Đóng gói MCW Core v1.5.1

Archive source này là bản phân phối độc lập `mcw-core 1.5.1`.

Python package gồm `mcw_core`, `src.core`, `src.models` và MCW LAN Agent đi kèm. Gói loại trừ `src.gui`, PySide6, tài khoản người dùng, cấu hình private, cache, instance, log và managed runtime.

Source archive của CurseForge gateway được phát hành riêng và chủ động không được đóng gói trong source archive hoặc wheel của MCW Core. MCW Core chỉ giữ phần client/cấu hình tích hợp gateway, không chứa secret triển khai hay endpoint mặc định.

Trước khi phát hành:

```bash
python -m tools.core_release_preflight
python -m pytest test -q
python -m compileall -q mcw_core src tools test examples
python -m pip wheel --no-deps --no-build-isolation .
```
