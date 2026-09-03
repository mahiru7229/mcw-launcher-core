# Hướng dẫn tạo theme cho MCW Launcher

Tài liệu này hướng dẫn tạo theme ngoài EXE cho MCW Launcher. Từ v0.11.0-alpha.1, theme có thể kèm PNG spritesheet animation; từ v0.11.0-alpha.2, theme có thể đóng gói font TTF/OTF cho toàn bộ chữ; từ v0.11.0-alpha.4, theme có thể điều khiển chuyển động giao diện.

## 1. Tạo thư mục theme

```text
themes/
└── my-theme/
    └── theme.json
```

`my-theme` là ID thư mục. Nên dùng chữ thường, số và dấu gạch ngang.

## 2. Tạo manifest

```json
{
  "schema_version": 5,
  "id": "my-theme",
  "name": "My Theme",
  "author": "Artist name",
  "description": "A custom MCW Launcher theme.",
  "assets": {}
}
```

Các field `id`, `name`, `author` chỉ là metadata hiển thị. `assets` ánh xạ key launcher tới đường dẫn PNG tương đối bên trong theme.

## 3. Bắt đầu từ một asset nhỏ

Theme không cần đủ toàn bộ file. Ví dụ chỉ thay background và logo:

```text
themes/my-theme/
├── theme.json
├── backgrounds/
│   └── window.png
└── logos/
    └── main.png
```

```json
{
  "schema_version": 1,
  "id": "my-theme",
  "name": "My Theme",
  "author": "Artist name",
  "assets": {
    "background.window": "backgrounds/window.png",
    "logo.main": "logos/main.png"
  }
}
```

Mọi widget khác tiếp tục dùng CSS mặc định.

## 4. Asset cho Beta 9

Các màn hình mới có asset riêng:

```text
surfaces/cards/microsoft.png
surfaces/cards/java.png
surfaces/cards/lifecycle.png
surfaces/badges/locked.png
icons/actions/microsoft.png
icons/actions/java.png
icons/actions/backup.png
icons/actions/restore.png
```

Khai báo:

```json
{
  "assets": {
    "surface.microsoft_card": "surfaces/cards/microsoft.png",
    "surface.java_card": "surfaces/cards/java.png",
    "surface.lifecycle_card": "surfaces/cards/lifecycle.png",
    "badge.locked": "surfaces/badges/locked.png",
    "icon.action.microsoft": "icons/actions/microsoft.png",
    "icon.action.java": "icons/actions/java.png",
    "icon.action.backup": "icons/actions/backup.png",
    "icon.action.restore": "icons/actions/restore.png"
  }
}
```

Canvas chính xác được liệt kê trong [`THEME_ASSET_GUIDE.md`](THEME_ASSET_GUIDE.md).

## 5. Asset bảo mật Beta 10

```text
surfaces/cards/security.png       480 × 260
icons/actions/shield.png          24 × 24
icons/actions/reprotect.png       24 × 24
```

Khai báo:

```json
{
  "assets": {
    "surface.security_card": "surfaces/cards/security.png",
    "icon.action.shield": "icons/actions/shield.png",
    "icon.action.reprotect": "icons/actions/reprotect.png"
  }
}
```

Card security chứa nội dung động như số account protected/legacy/invalid, vì vậy không nên vẽ sẵn các con số hoặc trạng thái vào PNG.

## 6. PNG có chữ sẵn

Chỉ dùng cho chữ cố định. Ví dụ nút Launch đã vẽ chữ `LAUNCH`:

```json
{
  "assets": {
    "button.launch": "controls/buttons/launch/default.png"
  },
  "text_assets": {
    "control.launch": "button.launch",
    "control.cancel": "button.cancel"
  }
}
```

**Show static text over themed controls** mặc định tắt trong `v0.6.0`. Launcher chỉ ẩn chữ khi PNG hợp lệ đã được load; thiếu ảnh thì chữ tự quay lại. Người dùng có thể bật lại nếu muốn chữ Qt đè lên PNG.

Không vẽ sẵn nội dung thay đổi theo thời gian như username, tên instance, version, trạng thái tải hoặc error message.


## 7. Animation spritesheet trong v0.11.0-alpha.1

Theme có thể vẽ progress, trạng thái busy và các animated asset tương lai bằng PNG spritesheet:

```json
{
  "schema_version": 2,
  "animations": {
    "progress.chunk": {
      "type": "spritesheet",
      "path": "animations/progress/chunk.png",
      "fallback_asset": "progress.chunk",
      "frame_size": [16, 16],
      "frame_count": 8,
      "columns": 8,
      "frame_duration_ms": 80,
      "loop": true,
      "render_mode": "tile_x",
      "filtering": "nearest"
    }
  }
}
```

Theme schema 1 cũ vẫn hoạt động. Xem [`THEME_ANIMATION_GUIDE.md`](THEME_ANIMATION_GUIDE.md) để biết cách xếp frame, animation key, fallback và giới hạn an toàn.

## 8. Custom font trong v0.11.0-alpha.2

Đặt font vào thư mục theme và khai báo manifest schema 3:

```text
themes/my-theme/
├── theme.json
└── fonts/
    ├── ui-regular.ttf
    └── ui-bold.otf
```

```json
{
  "schema_version": 3,
  "font": {
    "files": [
      "fonts/ui-regular.ttf",
      "fonts/ui-bold.otf"
    ],
    "family": "My Pixel Font",
    "point_size": 10.5,
    "weight": 400,
    "letter_spacing": 0,
    "fallback_families": ["Segoe UI", "Arial"]
  }
}
```

Font được áp dụng cho toàn bộ chữ và đổi ngay khi preview theme. Font nên chứa glyph tiếng Việt; nếu thiếu, hãy khai báo `fallback_families`. Xem [`THEME_FONT_GUIDE.md`](THEME_FONT_GUIDE.md) để biết đầy đủ field và giới hạn an toàn.

## 9. Motion trong v0.11.0-alpha.5

Theme schema 5 có thể cấu hình chuyển trang, button, dialog, sidebar, Launch Control, toast và giới hạn FPS:

```json
{
  "schema_version": 5,
  "motion": {
    "page": {"type": "fade_slide", "duration_ms": 170, "easing": "out_cubic", "distance_px": 18},
    "button": {"hover_duration_ms": 100, "press_duration_ms": 70, "easing": "out_quad"},
    "dialog": {"type": "fade", "duration_ms": 160, "easing": "out_cubic"},
    "sidebar": {"duration_ms": 220, "easing": "out_cubic", "collapsed_width": 72},
    "launch_control": {"type": "fade", "duration_ms": 140, "easing": "out_cubic"},
    "toast": {"type": "slide_fade", "duration_ms": 180, "visible_duration_ms": 3000, "easing": "out_cubic", "distance_px": 24, "max_visible": 3},
    "performance": {"full_fps": 60, "reduced_fps": 30, "pause_when_hidden": true}
  }
}
```

Người dùng vẫn có thể chọn Full, Reduced hoặc Off. Xem [`THEME_MOTION_GUIDE.md`](THEME_MOTION_GUIDE.md) để biết loại transition và giới hạn hợp lệ.

## 10. Trạng thái button

Một nút nên có đủ state khi có thể:

```text
controls/buttons/launch/
├── default.png
├── hover.png
├── pressed.png
├── disabled.png
├── cancel.png
├── cancel_hover.png
├── cancel_pressed.png
└── cancel_disabled.png
```

Các state Launch thiếu sẽ fallback về CSS. Riêng state Cancel có bộ PNG fallback đi kèm launcher, nên nút vẫn hiện rõ khi theme cũ chưa khai báo asset mới.

## 11. Background và vùng an toàn

- `background.window`: 1600 × 900.
- Sidebar: 220 × 900.
- Right panel: 400 × 900.
- Center/page: 980 px chiều rộng.
- Không đặt chữ quan trọng sát mép vì cửa sổ có thể scale hoặc resize.
- Kiểm tra theme trên 1366 × 768 và 1600 × 900.

## 12. Kiểm tra theme

1. Đặt folder cạnh source hoặc cạnh EXE:

```text
MCW Launcher.exe
themes/
└── my-theme/
```

2. Mở **Launcher Settings → Appearance**.
3. Chọn theme.
4. Nhấn **Reload and preview theme**.
5. Dùng card **Theme motion preview** để kiểm tra progress, state và toast.
6. Kiểm tra Accounts, Instances, Launcher Settings, Mod Manager, Modrinth Browser và các dialog.

Nếu theme không xuất hiện:

- kiểm tra `theme.json` là JSON hợp lệ;
- kiểm tra `id` không rỗng;
- kiểm tra path dùng `/` hoặc path tương đối hợp lệ;
- kiểm tra file thật sự là PNG;
- không dùng `..`, drive letter hoặc path tuyệt đối.

## 13. Fallback và theme chưa hoàn chỉnh

Theme có thể được phát hành khi mới có vài PNG. Launcher không crash vì:

- file thiếu;
- PNG hỏng;
- canvas khác khuyến nghị;
- key lạ;
- asset không đọc được.

Asset lỗi bị bỏ qua riêng lẻ. Tuy vậy, nên test console/log để phát hiện typo trong manifest.

## 14. Đóng gói cùng release

Công cụ release tự copy toàn bộ `themes/`:

```powershell
python tools/build_release_zip.py --exe ".\dist\MCW Launcher.exe" --version "0.5.1"
```

Người dùng cũng có thể thêm theme mới vào folder `themes/` mà không cần rebuild EXE.

## Checklist cho theme author

```text
[ ] theme.json hợp lệ
[ ] ID theme duy nhất
[ ] Không có path tuyệt đối hoặc ..
[ ] PNG có alpha đúng
[ ] Background được test ở nhiều độ phân giải
[ ] Button có hover/pressed khi cần
[ ] PNG có chữ được khai báo trong text_assets
[ ] Nội dung động không bị vẽ cứng vào PNG
[ ] Font TTF/OTF nằm trong theme và có glyph tiếng Việt
[ ] Font thiếu glyph có fallback_families phù hợp
[ ] Thiếu asset/font vẫn fallback dễ đọc
[ ] Theme xuất hiện sau Reload and preview theme
```

## 13. Theme Authoring Toolkit trong v0.11.0-beta.2

Trong **Launcher Settings → Appearance**, theme có thể được validate, mở thư mục, nhân bản, import/export ZIP và live reload. Theme schema 6 còn hỗ trợ custom QSS cục bộ:

```json
{
  "schema_version": 6,
  "stylesheet": "styles.qss"
}
```

QSS không được dùng `@import` hoặc `url()`; asset hình ảnh tiếp tục đi qua catalog và manifest để launcher kiểm tra path, định dạng và fallback. Xem [`THEME_AUTHORING_TOOLKIT.md`](THEME_AUTHORING_TOOLKIT.md) và [`theme-template`](theme-template).

## 15. Runtime Contract và MCW Theme Studio

Từ `v0.11.0-rc.1`, schema 6, asset catalog 1, validation report 1 và package ZIP 1 được đóng băng. Theme editor không nên sao chép danh sách key hoặc giới hạn từ GUI; hãy đọc [`schema/theme.schema.v6.json`](schema/theme.schema.v6.json), [`schema/theme-assets.v1.json`](schema/theme-assets.v1.json) và [`THEME_RUNTIME_CONTRACT.md`](THEME_RUNTIME_CONTRACT.md).

Schema 6 yêu cầu ID dạng chữ thường như `my-pixel-theme`. Field cấp cao không thuộc contract sẽ bị từ chối. Schema 1–5 vẫn được launcher đọc để giữ tương thích với theme cũ.

## Màu chủ đạo và palette — RC2

Theme schema 6 có thể khai báo `palette` để Theme Studio và launcher hiểu màu theo vai trò thay vì phải tìm-thay thế mã màu trong QSS. Tất cả field đều optional; giá trị thiếu sẽ dùng palette mặc định an toàn.

```json
{
  "palette": {
    "primary": "#5b8def",
    "primary_hover": "#77a2ff",
    "primary_pressed": "#3f6fc7",
    "primary_text": "#ffffff",
    "focus": "#77a2ff",
    "selection": "#34598f",
    "selection_text": "#ffffff",
    "link": "#8bb2ff",
    "success": "#78c978",
    "warning": "#d6a93c",
    "error": "#c47a7a"
  }
}
```

Để một PNG hoặc animation đổi theo accent, thêm key của nó vào `accent_assets`:

```json
{
  "accent_assets": [
    "button.primary",
    "button.primary_hover",
    "button.primary_pressed",
    "progress.chunk",
    "progress.indeterminate"
  ]
}
```

Không thêm logo, ảnh nhân vật hoặc background vào danh sách nếu không muốn launcher nhuộm chúng. Trong Launcher Settings, **Dùng màu của theme** sử dụng `palette`; **Dùng màu tùy chỉnh** ghi đè nhóm primary nhưng giữ success/warning/error của theme.

## 16. Màu chữ trong v1.0.1

Theme schema 6 có thể khai báo nhóm màu chữ:

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

Các field đều không bắt buộc để theme cũ tiếp tục hoạt động. Hãy giữ `text_primary` đủ tương phản với nền chính. Không dùng các field này để thay thế màu `success`, `warning`, `error`, `link`, `selection_text` hoặc `primary_text`, vì những màu đó mang ý nghĩa riêng trong giao diện.
