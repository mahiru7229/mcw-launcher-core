# MCW Theme Animation Schema v1

MCW Launcher `v0.11.0-alpha.1` cho phép theme cung cấp animation dạng PNG spritesheet. Theme chỉ chứa ảnh và metadata; launcher chịu trách nhiệm phát frame, scale, clip, fallback và giới hạn an toàn. Theme không được chạy Python, JavaScript hoặc executable.

## 1. Cấu trúc thư mục

```text
themes/my-theme/
├── theme.json
└── animations/
    ├── progress/
    │   ├── chunk.png
    │   └── indeterminate.png
    └── states/
        └── busy.png
```

Mỗi spritesheet là một PNG gồm nhiều frame có cùng kích thước, xếp từ trái sang phải rồi xuống hàng tiếp theo.

## 2. Manifest schema 2

```json
{
  "schema_version": 2,
  "id": "my-theme",
  "name": "My Animated Theme",
  "author": "Artist name",
  "capabilities": {
    "animated_assets": true,
    "sprite_sheets": true,
    "animated_progress": true
  },
  "assets": {
    "progress.chunk": "controls/progress/chunk.png",
    "icon.state.busy": "icons/states/busy.png"
  },
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

Theme schema 1 cũ vẫn được hỗ trợ. Dùng schema 2 khi theme chỉ cần `animations`; schema 3 của Alpha 2 giữ nguyên toàn bộ animation field và bổ sung custom font.

## 3. Các field animation

| Field | Ý nghĩa |
|---|---|
| `type` | Hiện tại chỉ chấp nhận `spritesheet`. |
| `path` | Đường dẫn PNG tương đối trong thư mục theme. |
| `fallback_asset` | Key PNG tĩnh dùng khi animation không thể load. |
| `frame_size` | `[width, height]` của một frame. |
| `frame_count` | Tổng số frame, từ 1 đến 256. |
| `columns` | Số frame trên mỗi hàng. |
| `frame_duration_ms` | Thời gian mỗi frame, từ 16 đến 10000 ms. |
| `loop` | Có lặp lại hay không. |
| `render_mode` | `tile_x`, `stretch` hoặc `contain`. |
| `filtering` | `nearest` cho pixel art hoặc `smooth` cho artwork mềm. |

## 4. Animation key có sẵn trong Alpha 1

### `progress.chunk`

Animation của phần progress đã hoàn thành. `tile_x` phù hợp nhất cho texture pixel-art lặp ngang. Launcher clip animation theo phần trăm hiện tại.

### `progress.indeterminate`

Dùng khi chưa biết tổng tiến trình, ví dụ kiểm tra modpack, tìm Java hoặc chuẩn bị update. `stretch` phù hợp với một pulse chạy xuyên toàn thanh.

### `state.busy`

Icon trạng thái đang làm việc trong Launch Control. Nên dùng frame vuông và `contain`.

Animation engine không giới hạn key vào danh sách trên. Theme có thể khai báo key mới để các widget tương lai sử dụng mà không cần đổi định dạng manifest.

## 5. Cách vẽ spritesheet

Ví dụ animation 8 frame, mỗi frame `16 × 16`:

```text
Kích thước PNG: 128 × 16
columns: 8
frame_count: 8
frame_size: [16, 16]
```

Nếu dùng 4 cột và 2 hàng:

```text
Kích thước PNG: 64 × 32
columns: 4
frame_count: 8
frame_size: [16, 16]
```

Thứ tự frame:

```text
0 1 2 3
4 5 6 7
```

Không chừa khoảng trống giữa các frame trong Alpha 1.

## 6. Render mode

### `tile_x`

Lặp frame theo chiều ngang. Dùng cho progress chunk hoặc texture chạy liên tục.

### `stretch`

Kéo frame phủ toàn vùng widget. Dùng cho progress indeterminate được vẽ theo đúng tỷ lệ thanh.

### `contain`

Giữ tỷ lệ ảnh và căn giữa. Dùng cho spinner, icon trạng thái hoặc mascot.

## 7. Fallback

Launcher resolve theo thứ tự:

```text
animation của theme đang chọn
→ animation cùng key của mcw-default
→ fallback_asset tĩnh
→ CSS/widget mặc định
```

Theme thiếu animation vẫn tương thích. PNG lỗi chỉ vô hiệu đúng animation đó và không làm launcher dừng khởi động.

## 8. Giới hạn an toàn

- Chỉ nhận PNG spritesheet.
- Không nhận path tuyệt đối, drive letter hoặc `..` thoát khỏi thư mục theme.
- Tối đa 256 frame cho mỗi animation.
- Frame tối đa `4096 × 4096`.
- Toàn spritesheet vẫn phải nằm trong giới hạn PNG `16384 × 16384`.
- Spritesheet phải đủ diện tích cho `frame_count`, `columns` và `frame_size` đã khai báo.
- Không hỗ trợ script, URL từ xa hoặc executable.

## 9. Preview

1. Đặt theme vào `themes/<theme-id>/`.
2. Mở **Launcher Settings → Appearance**.
3. Chọn theme.
4. Nhấn **Reload and preview theme**.
5. Chạy một tác vụ có progress hoặc bắt đầu Launch để xem animation.

Launcher dùng một animation clock chung và chỉ repaint widget liên quan, thay vì tạo timer riêng cho từng frame.
