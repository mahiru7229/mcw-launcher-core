# MCW Theme Custom Font Schema

MCW Launcher `v0.11.0-alpha.2` cho phép mỗi theme đóng gói font riêng và áp dụng font đó cho toàn bộ chữ trong launcher. Người dùng không cần cài font vào Windows; launcher đăng ký font trong bộ nhớ khi theme được chọn và gỡ font khi chuyển theme.

## 1. Cấu trúc thư mục

```text
themes/my-theme/
├── theme.json
└── fonts/
    ├── ui-regular.ttf
    └── ui-bold.otf
```

Font phải nằm bên trong thư mục theme. Chỉ hỗ trợ `.ttf` và `.otf`.

## 2. Manifest schema 3

```json
{
  "schema_version": 3,
  "id": "my-theme",
  "name": "My Font Theme",
  "author": "Artist name",
  "capabilities": {
    "custom_font": true
  },
  "font": {
    "files": [
      "fonts/ui-regular.ttf",
      "fonts/ui-bold.otf"
    ],
    "family": "My Pixel Font",
    "point_size": 10.5,
    "weight": 400,
    "italic": false,
    "letter_spacing": 0,
    "fallback_families": [
      "Segoe UI",
      "Arial"
    ]
  },
  "assets": {}
}
```

Có thể dùng `"path": "fonts/ui.ttf"` thay cho `files` khi theme chỉ có một file font.

## 3. Các field

| Field | Ý nghĩa |
|---|---|
| `files` | Danh sách từ 1 đến 8 file TTF/OTF trong theme. |
| `path` | Cú pháp rút gọn cho một file font. |
| `family` | Tên family mong muốn. Nếu bỏ trống, launcher dùng family đầu tiên Qt đọc được. |
| `point_size` | Cỡ chữ mặc định, từ 6 đến 72 pt. |
| `weight` | Một trong `100, 200, 300, 400, 500, 600, 700, 800, 900`. |
| `italic` | Bật chữ nghiêng mặc định. |
| `letter_spacing` | Khoảng cách chữ theo pixel, từ `-5` đến `20`. |
| `fallback_families` | Tối đa 8 font hệ thống dùng khi thiếu glyph. |

Style riêng của launcher vẫn có thể thay đổi kích thước hoặc weight cho title, badge và button. Theme font quyết định family nền cho toàn bộ widget, dialog, splash, log và tooltip.

## 4. Font nhiều weight

Một font family có thể chia thành nhiều file:

```json
{
  "font": {
    "files": [
      "fonts/pixel-regular.ttf",
      "fonts/pixel-medium.ttf",
      "fonts/pixel-bold.ttf"
    ],
    "family": "Pixel UI",
    "weight": 400
  }
}
```

Khi QSS yêu cầu `font-weight: 700`, Qt sẽ chọn face Bold đã đăng ký nếu font cung cấp face đó.

## 5. Tiếng Việt và fallback glyph

Font theme nên có đầy đủ glyph tiếng Việt. Nếu font pixel chỉ có ASCII, hãy khai báo fallback:

```json
{
  "font": {
    "path": "fonts/pixel.ttf",
    "family": "Pixel UI",
    "fallback_families": ["Segoe UI", "Arial"]
  }
}
```

Launcher không tự ghép glyph vào file font. Qt sẽ chọn family fallback cho ký tự mà font chính không có.

## 6. Fallback khi font lỗi

Launcher xử lý theo thứ tự:

```text
font của theme đang chọn
→ font của mcw-default nếu được khai báo
→ font hệ thống ban đầu của Qt
```

Nếu Qt từ chối file font, launcher tiếp tục chạy bằng font hệ thống. Theme cũ schema 1 hoặc schema 2 không cần sửa.

## 7. Giới hạn an toàn

- Chỉ nhận `.ttf` và `.otf`.
- Không nhận URL, path tuyệt đối, drive letter hoặc `..` thoát khỏi theme.
- Tối đa 8 file font.
- Tối đa 16 MiB cho mỗi file.
- Tối đa 32 MiB tổng font của một theme.
- Kiểm tra signature TTF/OTF trước khi giao file cho Qt.
- Theme không được chạy script hoặc executable.

## 8. Preview

1. Đặt theme vào `themes/<theme-id>/`.
2. Mở **Launcher Settings → Appearance**.
3. Chọn theme.
4. Nhấn **Reload and preview theme**.
5. Kiểm tra title, button, input, dialog, log và chữ tiếng Việt.

Font đổi ngay khi preview, không cần restart launcher.
