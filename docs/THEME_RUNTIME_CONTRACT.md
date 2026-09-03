# MCW Theme Runtime Contract v1

## Tiếng Việt

MCW Launcher `v0.11.0-rc.1` đóng băng giao kèo theme để MCW Theme Studio và các công cụ bên ngoài có thể tạo theme mà không phải sao chép logic từ GUI launcher.

### Các phiên bản đã chốt

| Thành phần | Phiên bản |
|---|---:|
| Runtime contract | `1` |
| Theme manifest schema | `6` |
| Asset catalog | `1` |
| Theme package ZIP | `1` |
| Validation report | `1` |

Theme schema 6 không đổi tên field, không đổi ý nghĩa field và không xóa asset key trong dòng `v0.11.x`. Thay đổi phá tương thích phải dùng schema mới. Launcher tiếp tục đọc schema 1–5 để giữ tương thích với theme cũ.

### Tệp máy có thể đọc

Các tệp sau nằm trong [`docs/schema`](schema):

- [`theme.schema.v6.json`](schema/theme.schema.v6.json): JSON Schema Draft 2020-12 cho `theme.json`.
- [`theme-assets.v1.json`](schema/theme-assets.v1.json): danh mục asset key, đường dẫn gợi ý, kích thước và mục đích.
- [`theme-runtime-contract.v1.json`](schema/theme-runtime-contract.v1.json): descriptor liên kết schema, catalog, package và validation report.

Có thể tạo lại chính xác ba tệp bằng:

```bash
python tools/export_theme_contract.py
```

### Validation report

Core validator không phụ thuộc PySide6:

```python
from pathlib import Path
from src.core.theme import ThemeValidator

report = ThemeValidator().validate_directory(Path("themes/my-theme"))
print(report.to_dict())
```

CLI tương đương, phù hợp cho editor hoặc CI:

```bash
python tools/validate_theme.py themes/my-theme --json
```

Mỗi issue có cấu trúc ổn định:

```json
{
  "severity": "error",
  "category": "asset",
  "code": "THEME_ASSET_UNKNOWN_KEY",
  "field": "assets.icon.example",
  "message": "Unknown asset key: icon.example"
}
```

`message` dành cho con người; Theme Studio nên quyết định hành vi dựa trên `code`, `field`, `severity` và version của report.

### Package ZIP v1

Export RC 1 có các đặc điểm:

- thứ tự file và timestamp ZIP cố định;
- cùng nội dung theme tạo cùng byte ZIP trong cùng runtime;
- đường dẫn dùng `/`;
- permission entry cố định;
- `theme-checksums.json` dùng SHA-256;
- checksum không tự bao gồm chính `theme-checksums.json`;
- import kiểm tra file thiếu, file thừa, checksum sai và theme ID không khớp;
- package Beta 2 dùng trường `sha256` vẫn được hỗ trợ khi import.

Cấu trúc chuẩn:

```text
my-theme.zip
└── my-theme/
    ├── theme.json
    ├── theme-checksums.json
    ├── styles.qss
    ├── fonts/
    ├── icons/
    └── animations/
```

### Quy tắc tương thích

- Schema 6 yêu cầu theme ID dạng chữ thường: `a-z`, `0-9`, `.`, `_`, `-`.
- Schema 6 từ chối field cấp cao không thuộc contract.
- Schema 1–5 giữ hành vi tương thích cũ.
- Theme không được chạy Python, JavaScript hoặc executable.
- Core theme không import `PySide6` hay `src.gui`.
- Theme Studio có thể tái sử dụng trực tiếp `src/core/theme` hoặc chỉ dùng các JSON contract.

---

## English

MCW Launcher `v0.11.0-rc.1` freezes the theme contract so MCW Theme Studio and external tools can create packages without copying launcher GUI logic.

### Frozen versions

| Component | Version |
|---|---:|
| Runtime contract | `1` |
| Theme manifest schema | `6` |
| Asset catalog | `1` |
| Theme package ZIP | `1` |
| Validation report | `1` |

Schema 6 fields will not be renamed, reinterpreted, or removed during the `v0.11.x` line. Breaking changes require a new schema version. Schemas 1–5 remain readable for backward compatibility.

### Machine-readable files

[`docs/schema`](schema) contains:

- [`theme.schema.v6.json`](schema/theme.schema.v6.json), a Draft 2020-12 JSON Schema for `theme.json`;
- [`theme-assets.v1.json`](schema/theme-assets.v1.json), the stable asset slot catalog;
- [`theme-runtime-contract.v1.json`](schema/theme-runtime-contract.v1.json), the contract descriptor and document hashes.

Regenerate them with:

```bash
python tools/export_theme_contract.py
```

### Stable validation API

`ThemeValidator` and the package helpers live under `src/core/theme` and do not depend on Qt. Validation reports expose versioned dictionaries and stable issue codes. Tooling should use codes and fields for behavior while treating messages as display text.

A CLI bridge is also available:

```bash
python tools/validate_theme.py themes/my-theme --json
```

### Deterministic package format

Package v1 fixes ZIP ordering, timestamps, permissions, path separators, and checksum structure. Imports reject missing, extra, modified, duplicated, unsafe, or mismatched files. Beta 2 checksum manifests remain import-compatible.

## RC2 optional palette extension

`v0.11.0-rc.2` adds two optional schema 6 fields without changing any frozen field:

```json
{
  "palette": {
    "primary": "#63984a",
    "primary_hover": "#7db45e",
    "primary_pressed": "#4d7938",
    "primary_text": "#ffffff",
    "focus": "#8ed35b",
    "selection": "#4f6d3c",
    "selection_text": "#ffffff",
    "link": "#8ed35b",
    "success": "#8ed35b",
    "warning": "#d6a93c",
    "error": "#c47a7a"
  },
  "accent_assets": [
    "button.primary",
    "progress.chunk"
  ]
}
```

Mọi màu dùng định dạng `#RRGGBB`. `accent_assets` là danh sách opt-in: launcher chỉ nhuộm những PNG hoặc spritesheet được theme chủ động liệt kê. Logo, hình nền và icon không bị đổi màu ngoài ý muốn. Khi người dùng chọn màu tùy chỉnh, nhóm primary/focus/selection/link được tạo từ màu đó; success, warning và error vẫn giữ ý nghĩa màu của theme.

These fields are optional and therefore remain compatible with the frozen schema 6 policy. Themes without `palette` keep their existing QSS and PNG appearance. A user custom accent may still override primary controls, but assets are tinted only when explicitly listed in `accent_assets`.

## v1.0.1 text palette extension

MCW Launcher `v1.0.1` extends the optional schema 6 palette with four backward-compatible text roles:

```json
{
  "palette": {
    "text_primary": "#f4f4f4",
    "text_muted": "#b8b8b8",
    "text_disabled": "#777777",
    "text_inverse": "#111111"
  }
}
```

- `text_primary` is the normal launcher text color.
- `text_muted` is used for descriptions, hints, and secondary labels.
- `text_disabled` is used for unavailable controls.
- `text_inverse` is available for text rendered against a contrasting surface.

Themes that omit these fields receive safe defaults. Launcher Settings may override the primary text family at runtime; success, warning, error, link, selection, and text-on-primary colors remain separate semantic roles. Theme authors should keep primary text readable against the theme background and should test both normal and disabled controls.

### Tiếng Việt

MCW Launcher `v1.0.1` bổ sung bốn vai trò màu chữ tùy chọn, vẫn tương thích với theme schema 6 cũ:

- `text_primary`: màu chữ thông thường.
- `text_muted`: mô tả, gợi ý và nhãn phụ.
- `text_disabled`: control đang bị vô hiệu hóa.
- `text_inverse`: chữ trên bề mặt có độ sáng đối nghịch.

Theme không khai báo các field này sẽ dùng giá trị mặc định an toàn. Màu chữ tùy chỉnh trong Launcher Settings chỉ thay thế nhóm chữ chính; màu success, warning, error, link, selection và chữ trên nút primary vẫn giữ vai trò ngữ nghĩa riêng.
