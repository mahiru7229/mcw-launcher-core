# Đóng gói và phát hành MCW Core 1.0.1

## Kết quả audit từ file được cung cấp

1. Wheel metadata khai báo version `1.0.0`.
2. Wheel được upload có `src/config.py` báo `1.0.0-rc.1`, nên `mcw_core.__version__` có thể trả RC1 dù package metadata là stable.
3. Repo core rút gọn chỉ include `mcw_core*`, nhưng `mcw_core` hiện import nhiều lớp từ `src`.
4. Launcher source đầy đủ có pyproject include `mcw_core*`, `src`, `src.core*`, `src.models*`, `src.database*` và exclude GUI.

Trước khi publish chính thức, phải đồng bộ version runtime và metadata.

## Public package 1.0.0 nên chứa

```toml
[tool.setuptools.packages.find]
include = ["mcw_core*", "src", "src.core*", "src.models*", "src.database*"]
exclude = ["src.gui*", "test*"]
```

Đây là giải pháp compatibility cho 1.0.0. Mục tiêu dài hạn nên chuyển implementation thật vào namespace private của `mcw_core`, sau đó bỏ `src` khỏi wheel ở major release phù hợp.

## Build

```powershell
python -m pip install build wheel
python -m build
```

Kiểm tra wheel trong môi trường sạch:

```powershell
py -3.12 -m venv .venv-test
.\.venv-test\Scripts\Activate.ps1
python -m pip install dist\mcw_core-1.0.1-py3-none-any.whl
python -c "import mcw_core; print(mcw_core.__version__)"
python -c "import importlib.util; assert importlib.util.find_spec('PySide6') is None"
```

## Release validation

- `mcw_core.__version__ == "1.0.0"`;
- package metadata version 1.0.0;
- import không cần PySide6;
- LAN Agent resource tồn tại và checksum đúng;
- CLI `mcw-core-launch --help` chạy;
- examples compile;
- public API tests xanh;
- GUI không import `src.core`;
- wheel không chứa account database, config, logs hoặc test data.

## API stability

- top-level `mcw_core`: stable;
- `mcw_core.api.*`: public granular boundary;
- `src.*`: implementation compatibility, không stable;
- deprecation cần ít nhất một minor release trước khi xóa public symbol.

## Distribution warning

Wheel chỉ là code MIT của project. Mod/modpack tải bởi người dùng vẫn tuân theo license và provider policy riêng.
