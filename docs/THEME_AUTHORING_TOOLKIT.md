# MCW Theme Authoring Toolkit

## Tiếng Việt

Từ MCW Launcher `v0.11.0-beta.2`, phần **Launcher Settings → Appearance** có bộ công cụ tạo và kiểm tra theme ngay trong launcher.

### Công cụ có sẵn

- **Validation details**: hiển thị lỗi/cảnh báo theo nhóm manifest, asset, animation, font, motion, stylesheet và security.
- **Open theme folder**: mở trực tiếp thư mục theme đang chọn.
- **Duplicate theme**: tạo bản sao có ID và tên mới. Đây là cách an toàn để bắt đầu từ `mcw-default` mà không sửa theme gốc.
- **Import theme ZIP**: nhập gói theme sau khi kiểm tra path traversal, symlink, file thực thi, số lượng file và dung lượng giải nén.
- **Export theme ZIP**: validate theme rồi tạo ZIP kèm `theme-checksums.json` chứa SHA-256 của từng file.
- **Live reload theme files**: theo dõi `theme.json`, QSS, PNG, TTF và OTF. Thay đổi được debounce trước khi kiểm tra và áp dụng.

Nếu file đang được chỉnh dở khiến theme không hợp lệ, live reload sẽ giữ theme hợp lệ gần nhất thay vì làm giao diện crash hoặc rơi về fallback ngay lập tức.

### Custom stylesheet — schema 6

Theme schema 6 có thể khai báo một file QSS riêng:

```json
{
  "schema_version": 6,
  "id": "my-theme",
  "name": "My Theme",
  "author": "Artist",
  "stylesheet": "styles.qss",
  "assets": {}
}
```

`styles.qss` được áp dụng sau stylesheet nền và trước font/PNG rules do launcher tạo. Vì lý do an toàn, custom QSS:

- tối đa 512 KiB;
- phải nằm trong thư mục theme;
- không được chứa `@import`, `url()` hoặc NUL;
- không thể tải file hoặc nội dung mạng;
- không thể chạy script.

Ảnh và font vẫn phải được khai báo qua `assets`, `animations` và `font` trong `theme.json`.

### Cấu trúc ZIP

Cả hai kiểu sau đều hợp lệ:

```text
my-theme.zip
└── my-theme/
    ├── theme.json
    ├── styles.qss
    ├── icons/
    └── fonts/
```

hoặc:

```text
my-theme.zip
├── theme.json
├── styles.qss
├── icons/
└── fonts/
```

ZIP không được chứa Python, JavaScript, EXE, DLL, BAT, CMD, PowerShell hoặc symlink.

### Quy trình đề xuất

1. Chọn `MCW Default PNG`.
2. Nhấn **Duplicate theme**.
3. Mở thư mục bản sao.
4. Bật **Live reload theme files**.
5. Chỉnh PNG, font, `theme.json` hoặc `styles.qss`.
6. Xem card preview và **Validation details**.
7. Nhấn **Export theme ZIP** khi không còn lỗi.

Mẫu tối thiểu nằm trong [`docs/theme-template`](theme-template).

---

## English

Starting with MCW Launcher `v0.11.0-beta.2`, **Launcher Settings → Appearance** includes an integrated theme authoring and validation toolkit.

### Available tools

- **Validation details** groups errors and warnings by manifest, asset, animation, font, motion, stylesheet, and security.
- **Open theme folder** opens the selected theme directory.
- **Duplicate theme** creates a copy with a new ID and display name.
- **Import theme ZIP** validates traversal, symlinks, executable files, file count, and uncompressed size before installation.
- **Export theme ZIP** validates the theme and includes `theme-checksums.json` with per-file SHA-256 hashes.
- **Live reload theme files** watches `theme.json`, QSS, PNG, TTF, and OTF files with debounce.

When an editor temporarily writes invalid JSON or metadata, live reload keeps the last valid theme active instead of crashing the UI.

### Custom stylesheet — schema 6

Schema 6 adds an optional local QSS file:

```json
{
  "schema_version": 6,
  "id": "my-theme",
  "name": "My Theme",
  "author": "Artist",
  "stylesheet": "styles.qss",
  "assets": {}
}
```

The stylesheet is limited to 512 KiB, must remain inside the theme directory, and may not contain `@import`, `url()`, or NUL. Images and fonts continue to use the validated manifest fields.

A minimal template is available in [`docs/theme-template`](theme-template).

---

## RC 1 contract freeze

MCW Launcher `v0.11.0-rc.1` đóng băng schema 6 và package format 1 để chuẩn bị cho MCW Theme Studio. Công cụ bên ngoài nên đọc [`THEME_RUNTIME_CONTRACT.md`](THEME_RUNTIME_CONTRACT.md) và các tệp trong [`docs/schema`](schema) thay vì hard-code asset key hoặc giới hạn runtime.

MCW Launcher `v0.11.0-rc.1` freezes schema 6 and package format 1 for MCW Theme Studio. External tools should consume [`THEME_RUNTIME_CONTRACT.md`](THEME_RUNTIME_CONTRACT.md) and the machine-readable files under [`docs/schema`](schema) instead of hard-coding runtime limits or asset keys.

## Palette and accent preview — RC2

The Appearance page now previews the effective accent and lets the user choose between the theme palette and a custom accent. Theme editors should expose the schema 6 `palette` object as semantic color fields and `accent_assets` as an opt-in asset checklist. Do not implement blanket recoloring: only listed assets are tintable.

The machine-readable source of truth remains `docs/schema/theme.schema.v6.json`. RC2 adds optional fields only, so existing schema 6 projects remain valid.
