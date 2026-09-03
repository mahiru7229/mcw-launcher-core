# MCW Launcher PNG Theme Asset Guide

Tài liệu này liệt kê toàn bộ PNG mà một theme có thể thay thế trong **MCW Launcher v0.5.1 Stable**. Mọi file đều là **tùy chọn**: thiếu, hỏng, sai định dạng hoặc nằm ngoài thư mục theme thì launcher chỉ bỏ qua asset đó và quay về CSS/text mặc định.

Tổng số asset key hiện tại: **119**.

## Cấu trúc theme

```text
themes/
└── <theme-id>/
    ├── theme.json
    ├── backgrounds/
    ├── controls/
    ├── icons/
    ├── logos/
    └── surfaces/
```

Canvas dưới đây là kích thước thiết kế khuyến nghị. Launcher có thể co giãn ảnh; nên giữ viền và nội dung quan trọng cách mép ít nhất 8–18 px.

## Asset mới trong Beta 9

Beta 9 bổ sung các vùng dành riêng cho Accounts, Java, Backup và Modpack lifecycle:

| Key | Canvas | Dùng cho |
|---|---:|---|
| `surface.microsoft_card` | 480 × 280 | Card thêm tài khoản Microsoft và trạng thái chờ phê duyệt. |
| `surface.java_card` | 480 × 260 | Card quét Java và hiển thị vendor/version/architecture. |
| `surface.lifecycle_card` | 480 × 440 | Card backup, restore và cập nhật modpack. |
| `badge.locked` | 260 × 48 | Badge tính năng bị khóa hoặc đang chờ approval. |
| `icon.action.microsoft` | 24 × 24 | Nút thêm tài khoản Microsoft. |
| `icon.action.java` | 24 × 24 | Nút quét Java. |
| `icon.action.backup` | 24 × 24 | Nút tạo backup. |
| `icon.action.restore` | 24 × 24 | Nút restore backup. |


## Asset mới trong Beta 10

| Key | Canvas | Dùng cho |
|---|---:|---|
| `surface.security_card` | 480 × 260 | Card kiểm tra DPAPI, record integrity và database security. |
| `icon.action.shield` | 24 × 24 | Nút Verify security. |
| `icon.action.reprotect` | 24 × 24 | Nút Re-protect credentials. |

## Danh sách PNG

| Key trong `theme.json` | Tên file / nơi lưu | Canvas | Nhóm | Mục đích |
|---|---|---:|---|---|
| `background.window` | `themes/<theme-id>/backgrounds/window.png` | **1600 × 900 px** | Background | Full launcher background, including unused outer areas. |
| `background.center` | `themes/<theme-id>/backgrounds/center.png` | **980 × 900 px** | Background | Center column behind pages and the launch control. |
| `background.sidebar` | `themes/<theme-id>/backgrounds/sidebar.png` | **220 × 900 px** | Background | Left navigation sidebar. |
| `background.right_panel` | `themes/<theme-id>/backgrounds/right_panel.png` | **400 × 900 px** | Background | Right session/status panel. |
| `background.launch_control` | `themes/<theme-id>/backgrounds/launch_control.png` | **980 × 120 px** | Background | Permanent launch bar at the bottom of the center column. |
| `background.page.home` | `themes/<theme-id>/backgrounds/pages/home.png` | **980 × 780 px** | Page background | Home page viewport. |
| `background.page.accounts` | `themes/<theme-id>/backgrounds/pages/accounts.png` | **980 × 780 px** | Page background | Accounts page viewport. |
| `background.page.instances` | `themes/<theme-id>/backgrounds/pages/instances.png` | **980 × 780 px** | Page background | Instances page viewport. |
| `background.page.instance_settings` | `themes/<theme-id>/backgrounds/pages/instance_settings.png` | **980 × 780 px** | Page background | Instance Settings page viewport. |
| `background.page.launcher_settings` | `themes/<theme-id>/backgrounds/pages/launcher_settings.png` | **980 × 780 px** | Page background | Launcher Settings page viewport. |
| `background.page.logs` | `themes/<theme-id>/backgrounds/pages/logs.png` | **980 × 780 px** | Page background | Logs page viewport. |
| `background.page.about` | `themes/<theme-id>/backgrounds/pages/about.png` | **980 × 780 px** | Page background | About page viewport. |
| `background.dialog.mod_manager` | `themes/<theme-id>/backgrounds/dialogs/mod_manager.png` | **1050 × 680 px** | Dialog background | Fabric Mod Manager dialog. |
| `background.dialog.modrinth` | `themes/<theme-id>/backgrounds/dialogs/modrinth.png` | **1120 × 720 px** | Dialog background | Modrinth mod and modpack browser. |
| `background.dialog.update` | `themes/<theme-id>/backgrounds/dialogs/update.png` | **680 × 520 px** | Dialog background | Update confirmation dialog. |
| `background.dialog.message` | `themes/<theme-id>/backgrounds/dialogs/message.png` | **520 × 260 px** | Dialog background | QMessageBox confirmation, warning and error dialogs. |
| `surface.microsoft_card` | `themes/<theme-id>/surfaces/cards/microsoft.png` | **480 × 280 px** | Surface | Account creation card with Microsoft approval status. |
| `surface.java_card` | `themes/<theme-id>/surfaces/cards/java.png` | **480 × 260 px** | Surface | Java installation scanner and diagnostics card. |
| `surface.lifecycle_card` | `themes/<theme-id>/surfaces/cards/lifecycle.png` | **480 × 440 px** | Surface | Backup and Modrinth pack lifecycle card. |
| `surface.card` | `themes/<theme-id>/surfaces/card.png` | **480 × 240 px** | Surface | Normal card. Designed as a stretchable nine-slice surface. |
| `surface.hero_card` | `themes/<theme-id>/surfaces/hero_card.png` | **920 × 230 px** | Surface | Large Home hero card. |
| `surface.inset` | `themes/<theme-id>/surfaces/inset.png` | **440 × 180 px** | Surface | Inset panels and secondary surfaces. |
| `surface.table` | `themes/<theme-id>/surfaces/table.png` | **920 × 500 px** | Surface | Table body background. |
| `surface.table_header` | `themes/<theme-id>/surfaces/table_header.png` | **920 × 40 px** | Surface | Table header row. |
| `surface.log` | `themes/<theme-id>/surfaces/log_output.png` | **920 × 560 px** | Surface | Launcher activity log output. |
| `surface.details` | `themes/<theme-id>/surfaces/details.png` | **920 × 260 px** | Surface | Read-only mod details and update release notes. |
| `surface.group_box` | `themes/<theme-id>/surfaces/group_box.png` | **480 × 180 px** | Surface | Group box background for current or future grouped controls. |
| `surface.tab_pane` | `themes/<theme-id>/surfaces/tabs/pane.png` | **920 × 500 px** | Tab | Tab content pane. |
| `surface.tab` | `themes/<theme-id>/surfaces/tabs/default.png` | **180 × 42 px** | Tab | Normal tab button. |
| `surface.tab_hover` | `themes/<theme-id>/surfaces/tabs/hover.png` | **180 × 42 px** | Tab | Hovered tab button. |
| `surface.tab_selected` | `themes/<theme-id>/surfaces/tabs/selected.png` | **180 × 42 px** | Tab | Selected tab button. |
| `surface.table_selected` | `themes/<theme-id>/surfaces/table_selected.png` | **920 × 40 px** | Surface | Selected table row or cell. |
| `surface.tooltip` | `themes/<theme-id>/surfaces/tooltip.png` | **360 × 120 px** | Surface | Launcher tooltip background. |
| `button.default` | `themes/<theme-id>/controls/buttons/default.png` | **240 × 48 px** | Button | Normal push button. |
| `button.hover` | `themes/<theme-id>/controls/buttons/hover.png` | **240 × 48 px** | Button | Hovered push button. |
| `button.pressed` | `themes/<theme-id>/controls/buttons/pressed.png` | **240 × 48 px** | Button | Pressed push button. |
| `button.disabled` | `themes/<theme-id>/controls/buttons/disabled.png` | **240 × 48 px** | Button | Disabled push button. |
| `button.primary` | `themes/<theme-id>/controls/buttons/primary.png` | **260 × 72 px** | Button | Primary action and Launch button. |
| `button.primary_hover` | `themes/<theme-id>/controls/buttons/primary_hover.png` | **260 × 72 px** | Button | Hovered primary action. |
| `button.primary_pressed` | `themes/<theme-id>/controls/buttons/primary_pressed.png` | **260 × 72 px** | Button | Pressed primary action. |
| `button.launch` | `themes/<theme-id>/controls/buttons/launch/default.png` | **461 × 133 px** | Launch button | Dedicated Launch button artwork; may contain baked pixel-art lettering. |
| `button.launch_hover` | `themes/<theme-id>/controls/buttons/launch/hover.png` | **461 × 133 px** | Launch button | Hovered Launch button artwork. |
| `button.launch_pressed` | `themes/<theme-id>/controls/buttons/launch/pressed.png` | **461 × 133 px** | Launch button | Pressed Launch button artwork. |
| `button.launch_disabled` | `themes/<theme-id>/controls/buttons/launch/disabled.png` | **461 × 133 px** | Launch button | Disabled Launch button artwork. |
| `button.cancel` | `themes/<theme-id>/controls/buttons/launch/cancel.png` | **461 × 133 px** | Launch button | Cancel artwork while a launch download is active. |
| `button.cancel_hover` | `themes/<theme-id>/controls/buttons/launch/cancel_hover.png` | **461 × 133 px** | Launch button | Hovered Cancel artwork. |
| `button.cancel_pressed` | `themes/<theme-id>/controls/buttons/launch/cancel_pressed.png` | **461 × 133 px** | Launch button | Pressed Cancel artwork. |
| `button.cancel_disabled` | `themes/<theme-id>/controls/buttons/launch/cancel_disabled.png` | **461 × 133 px** | Launch button | Disabled Cancel artwork while pause is being applied. |
| `button.danger` | `themes/<theme-id>/controls/buttons/danger.png` | **240 × 48 px** | Button | Destructive action. |
| `button.danger_hover` | `themes/<theme-id>/controls/buttons/danger_hover.png` | **240 × 48 px** | Button | Hovered destructive action. |
| `button.nav` | `themes/<theme-id>/controls/navigation/default.png` | **192 × 46 px** | Navigation | Normal sidebar navigation button. |
| `button.nav_hover` | `themes/<theme-id>/controls/navigation/hover.png` | **192 × 46 px** | Navigation | Hovered sidebar navigation button. |
| `button.nav_selected` | `themes/<theme-id>/controls/navigation/selected.png` | **192 × 46 px** | Navigation | Selected sidebar navigation button. |
| `input.default` | `themes/<theme-id>/controls/input/default.png` | **420 × 42 px** | Input | Line edit, combo box and spin box background. |
| `input.focus` | `themes/<theme-id>/controls/input/focus.png` | **420 × 42 px** | Input | Focused single-line input background. |
| `input.text_area` | `themes/<theme-id>/controls/input/text_area.png` | **640 × 140 px** | Input | Multiline JVM and game argument editor. |
| `input.text_area_focus` | `themes/<theme-id>/controls/input/text_area_focus.png` | **640 × 140 px** | Input | Focused multiline argument editor. |
| `combo.popup` | `themes/<theme-id>/controls/combo/popup.png` | **420 × 320 px** | Control | Combo box drop-down list surface. |
| `checkbox.unchecked` | `themes/<theme-id>/controls/checkbox/unchecked.png` | **24 × 24 px** | Control | Unchecked checkbox indicator. |
| `checkbox.checked` | `themes/<theme-id>/controls/checkbox/checked.png` | **24 × 24 px** | Control | Checked checkbox indicator. |
| `checkbox.disabled` | `themes/<theme-id>/controls/checkbox/disabled.png` | **24 × 24 px** | Control | Disabled checkbox indicator. |
| `combo.arrow` | `themes/<theme-id>/controls/combo/arrow.png` | **20 × 20 px** | Control | Combo box drop-down arrow. |
| `progress.track` | `themes/<theme-id>/controls/progress/track.png` | **640 × 24 px** | Progress | Progress bar track. |
| `progress.chunk` | `themes/<theme-id>/controls/progress/chunk.png` | **640 × 24 px** | Progress | Progress bar filled chunk. |
| `scrollbar.track` | `themes/<theme-id>/controls/scrollbar/track.png` | **16 × 256 px** | Scrollbar | Vertical scrollbar track. |
| `scrollbar.handle` | `themes/<theme-id>/controls/scrollbar/handle.png` | **16 × 64 px** | Scrollbar | Vertical scrollbar handle. |
| `scrollbar.horizontal_track` | `themes/<theme-id>/controls/scrollbar/horizontal_track.png` | **256 × 16 px** | Scrollbar | Horizontal scrollbar track. |
| `scrollbar.horizontal_handle` | `themes/<theme-id>/controls/scrollbar/horizontal_handle.png` | **64 × 16 px** | Scrollbar | Horizontal scrollbar handle. |
| `badge.status` | `themes/<theme-id>/surfaces/badges/status.png` | **180 × 40 px** | Badge | Ready/success status badge. |
| `badge.warning` | `themes/<theme-id>/surfaces/badges/warning.png` | **180 × 40 px** | Badge | Warning status badge. |
| `badge.locked` | `themes/<theme-id>/surfaces/badges/locked.png` | **260 × 48 px** | Badge | Feature locked or approval-pending status badge. |
| `badge.error` | `themes/<theme-id>/surfaces/badges/error.png` | **180 × 40 px** | Badge | Error/failed status badge. |
| `logo.main` | `themes/<theme-id>/logos/main.png` | **640 × 240 px** | Logo | Large Home page launcher logo. |
| `logo.sidebar` | `themes/<theme-id>/logos/sidebar.png` | **192 × 72 px** | Logo | Optional sidebar brand logo. |
| `icon.app` | `themes/<theme-id>/icons/app.png` | **256 × 256 px** | Application | Window and executable icon source. |
| `icon.nav.home` | `themes/<theme-id>/icons/navigation/home.png` | **32 × 32 px** | Navigation icon | Home navigation icon. |
| `icon.nav.accounts` | `themes/<theme-id>/icons/navigation/accounts.png` | **32 × 32 px** | Navigation icon | Accounts navigation icon. |
| `icon.nav.instances` | `themes/<theme-id>/icons/navigation/instances.png` | **32 × 32 px** | Navigation icon | Instances navigation icon. |
| `icon.nav.instance_settings` | `themes/<theme-id>/icons/navigation/instance_settings.png` | **32 × 32 px** | Navigation icon | Instance Settings navigation icon. |
| `icon.nav.launcher_settings` | `themes/<theme-id>/icons/navigation/launcher_settings.png` | **32 × 32 px** | Navigation icon | Launcher Settings navigation icon. |
| `icon.nav.logs` | `themes/<theme-id>/icons/navigation/logs.png` | **32 × 32 px** | Navigation icon | Logs navigation icon. |
| `icon.nav.about` | `themes/<theme-id>/icons/navigation/about.png` | **32 × 32 px** | Navigation icon | About navigation icon. |
| `icon.action.launch` | `themes/<theme-id>/icons/actions/launch.png` | **40 × 40 px** | Action icon | Launch button. |
| `icon.action.refresh` | `themes/<theme-id>/icons/actions/refresh.png` | **24 × 24 px** | Action icon | Refresh/reload actions. |
| `icon.action.add` | `themes/<theme-id>/icons/actions/add.png` | **24 × 24 px** | Action icon | Create/add actions. |
| `icon.action.remove` | `themes/<theme-id>/icons/actions/remove.png` | **24 × 24 px** | Action icon | Remove/delete actions. |
| `icon.action.edit` | `themes/<theme-id>/icons/actions/edit.png` | **24 × 24 px** | Action icon | Rename/edit actions. |
| `icon.action.clone` | `themes/<theme-id>/icons/actions/clone.png` | **24 × 24 px** | Action icon | Clone/copy instance action. |
| `icon.action.import` | `themes/<theme-id>/icons/actions/import.png` | **24 × 24 px** | Action icon | Import package action. |
| `icon.action.export` | `themes/<theme-id>/icons/actions/export.png` | **24 × 24 px** | Action icon | Export package/diagnostics action. |
| `icon.action.folder` | `themes/<theme-id>/icons/actions/folder.png` | **24 × 24 px** | Action icon | Open or browse folder/file action. |
| `icon.action.save` | `themes/<theme-id>/icons/actions/save.png` | **24 × 24 px** | Action icon | Save settings action. |
| `icon.action.reset` | `themes/<theme-id>/icons/actions/reset.png` | **24 × 24 px** | Action icon | Reset settings action. |
| `icon.action.search` | `themes/<theme-id>/icons/actions/search.png` | **24 × 24 px** | Action icon | Search action. |
| `icon.action.previous` | `themes/<theme-id>/icons/actions/previous.png` | **24 × 24 px** | Action icon | Previous page action. |
| `icon.action.next` | `themes/<theme-id>/icons/actions/next.png` | **24 × 24 px** | Action icon | Next page action. |
| `icon.action.download` | `themes/<theme-id>/icons/actions/download.png` | **24 × 24 px** | Action icon | Install/download action. |
| `icon.action.update` | `themes/<theme-id>/icons/actions/update.png` | **24 × 24 px** | Action icon | Check/apply update action. |
| `icon.action.modrinth` | `themes/<theme-id>/icons/actions/modrinth.png` | **24 × 24 px** | Action icon | Browse Modrinth action. |
| `icon.action.mods` | `themes/<theme-id>/icons/actions/mods.png` | **24 × 24 px** | Action icon | Manage mods action. |
| `icon.action.enable` | `themes/<theme-id>/icons/actions/enable.png` | **24 × 24 px** | Action icon | Enable mod action. |
| `icon.action.disable` | `themes/<theme-id>/icons/actions/disable.png` | **24 × 24 px** | Action icon | Disable mod action. |
| `icon.action.microsoft` | `themes/<theme-id>/icons/actions/microsoft.png` | **24 × 24 px** | Action icon | Add Microsoft account action. |
| `icon.action.java` | `themes/<theme-id>/icons/actions/java.png` | **24 × 24 px** | Action icon | Scan or manage Java installations. |
| `icon.action.backup` | `themes/<theme-id>/icons/actions/backup.png` | **24 × 24 px** | Action icon | Create an instance or world backup. |
| `icon.action.restore` | `themes/<theme-id>/icons/actions/restore.png` | **24 × 24 px** | Action icon | Restore an MCW backup. |
| `icon.action.account` | `themes/<theme-id>/icons/actions/account.png` | **24 × 24 px** | Action icon | Account action. |
| `icon.action.instance` | `themes/<theme-id>/icons/actions/instance.png` | **24 × 24 px** | Action icon | Instance action. |
| `icon.action.settings` | `themes/<theme-id>/icons/actions/settings.png` | **24 × 24 px** | Action icon | Settings action. |
| `icon.action.copy` | `themes/<theme-id>/icons/actions/copy.png` | **24 × 24 px** | Action icon | Copy text action. |
| `icon.action.clear` | `themes/<theme-id>/icons/actions/clear.png` | **24 × 24 px** | Action icon | Clear output action. |
| `icon.action.repair` | `themes/<theme-id>/icons/actions/repair.png` | **24 × 24 px** | Action icon | Repair Fabric/instance action. |
| `icon.action.language` | `themes/<theme-id>/icons/actions/language.png` | **24 × 24 px** | Action icon | Reload language packs action. |
| `icon.action.theme` | `themes/<theme-id>/icons/actions/theme.png` | **24 × 24 px** | Action icon | Reload/apply theme action. |
| `icon.action.release` | `themes/<theme-id>/icons/actions/release.png` | **24 × 24 px** | Action icon | Open GitHub release page. |
| `icon.state.ready` | `themes/<theme-id>/icons/states/ready.png` | **32 × 32 px** | State icon | Ready state. |
| `icon.state.busy` | `themes/<theme-id>/icons/states/busy.png` | **32 × 32 px** | State icon | Busy/downloading state. |
| `icon.state.success` | `themes/<theme-id>/icons/states/success.png` | **32 × 32 px** | State icon | Success/running state. |
| `icon.state.warning` | `themes/<theme-id>/icons/states/warning.png` | **32 × 32 px** | State icon | Warning state. |
| `icon.state.error` | `themes/<theme-id>/icons/states/error.png` | **32 × 32 px** | State icon | Failure state. |

| `surface.security_card` | `themes/<theme-id>/surfaces/cards/security.png` | **480 × 260 px** | Surface | Account security and credential protection card. |
| `icon.action.shield` | `themes/<theme-id>/icons/actions/shield.png` | **24 × 24 px** | Action icon | Verify account database and credential protection. |
| `icon.action.reprotect` | `themes/<theme-id>/icons/actions/reprotect.png` | **24 × 24 px** | Action icon | Re-protect Microsoft credentials. |

## Quy tắc xuất PNG

- Dùng PNG RGBA; nền trong suốt được hỗ trợ.
- Không dùng đường dẫn tuyệt đối, `..`, symlink hoặc file nằm ngoài `themes/<theme-id>/`.
- Có thể bỏ qua bất kỳ asset nào chưa thiết kế; launcher fallback riêng cho đúng thành phần đó.
- Background toàn cửa sổ nên vẽ theo canvas 1600 × 900 và giữ nội dung quan trọng trong vùng an toàn.
- Button/card/input/badge có thể bị kéo giãn; tránh vẽ chữ hoặc chi tiết quan trọng sát mép.
- Icon 24 × 24 và 32 × 32 nên chừa 2–4 px trong suốt quanh hình.
- Pixel art nên được kiểm tra ở DPI 100%, 125%, 150% và 200% để tránh mờ hoặc lệch viền.

## Hiển thị chữ tĩnh trên PNG

Một số PNG có thể vẽ sẵn chữ cố định, ví dụ nút Launch có chữ `LAUNCH`. Khai báo semantic role trong `theme.json`:

```json
{
  "text_assets": {
    "control.launch": "button.launch",
    "control.cancel": "button.cancel"
  }
}
```

Trong **Launcher Settings → Appearance**, tùy chọn **Show static text over themed controls** quyết định Qt có vẽ thêm chữ hay không. Tùy chọn này mặc định **tắt** trong `v0.6.0`.

- Bật: luôn vẽ chữ Qt.
- Tắt (mặc định): chỉ ẩn chữ của control đã được khai báo trong `text_assets`.
- Nếu PNG tương ứng thiếu hoặc hỏng, chữ tự xuất hiện lại.
- Nội dung động như tên instance, version, progress, trạng thái và lỗi không bị ẩn.

| Static role | Asset xác nhận | Thành phần |
|---|---|---|
| `control.launch` | `button.launch` | Nút Launch cố định ở thanh dưới. |
| `control.cancel` | `button.cancel` | Nút Cancel xuất hiện trong lúc Launch đang tải hoặc chuẩn bị file. |

## Theme manifest mẫu

```json
{
  "schema_version": 1,
  "id": "my-pixel-theme",
  "name": "My Pixel Theme",
  "author": "Artist name",
  "description": "Optional pixel-art overrides for MCW Launcher.",
  "assets": {
    "background.window": "backgrounds/window.png",
    "surface.microsoft_card": "surfaces/cards/microsoft.png",
    "surface.java_card": "surfaces/cards/java.png",
    "surface.lifecycle_card": "surfaces/cards/lifecycle.png",
    "badge.locked": "surfaces/badges/locked.png",
    "button.launch": "controls/buttons/launch/default.png",
    "button.cancel": "controls/buttons/launch/cancel.png",
    "button.cancel_hover": "controls/buttons/launch/cancel_hover.png",
    "button.cancel_pressed": "controls/buttons/launch/cancel_pressed.png",
    "button.cancel_disabled": "controls/buttons/launch/cancel_disabled.png",
    "icon.action.backup": "icons/actions/backup.png"
  },
  "text_assets": {
    "control.launch": "button.launch",
    "control.cancel": "button.cancel"
  }
}
```

Không cần khai báo asset chưa có. `themes/mcw-default/theme.json` trong repo là manifest tham khảo đầy đủ.

## Fallback

Khi theme hoặc PNG không tải được:

1. Launcher vẫn tiếp tục khởi động.
2. Chỉ asset lỗi bị bỏ qua.
3. Widget tương ứng dùng stylesheet mặc định.
4. Logo/icon lỗi quay về text hoặc trạng thái không icon.
5. Người dùng vẫn có thể đổi theme hoặc nhấn reload trong Launcher Settings.

## Ngoại lệ hệ điều hành

File picker native của Windows (`QFileDialog`) do Windows vẽ nên không thể thay hoàn toàn bằng PNG theme. Các nút mở file/folder nằm bên trong MCW Launcher vẫn nhận icon và button theme bình thường.

Xem hướng dẫn từng bước tại [`THEME_CREATION_GUIDE.md`](THEME_CREATION_GUIDE.md).
