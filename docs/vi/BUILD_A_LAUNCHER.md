# Bản thiết kế xây launcher bằng MCW Core

## 1. Kiến trúc đề xuất

```text
GUI/View
  ↓ signal/command
Controller
  ↓ validate + create request
Task Runner / Worker Pool
  ↓ blocking call
MCW Core public API
  ↓ result / typed exception / progress
Controller
  ↓ presenter/view model
GUI
```

Không để View import provider client, database hoặc filesystem implementation.

## 2. App composition root

```python
from mcw_core import CorePaths, MCWCore

class ApplicationServices:
    def __init__(self, root):
        self.core = MCWCore(CorePaths.from_root(root))
        self.pool = ThreadPoolExecutor(max_workers=4)
```

## 3. Task runner contract

Mỗi task cần:

- `task_id` duy nhất;
- callable blocking;
- cờ blocking/non-blocking;
- started/succeeded/failed/settled event;
- chống chạy trùng task;
- đảm bảo cleanup thread;
- cancellation đi qua `core.operations`.

Pseudo-interface:

```python
runner.run(
    task_id="minecraft.launch",
    task=lambda: core.launch(request),
    message="Launching...",
    blocking=True,
)
```

## 4. Controllers

### InstanceController

- list/refresh;
- select/load;
- create/change loader;
- import/export;
- status/health;
- icon/rename/clone/delete.

### LaunchController

- giữ selected instance/account;
- validate trước task;
- begin operation;
- tạo `LaunchRequest`;
- progress bridge;
- handle result;
- handle on_exit;
- pause/resume/cancel.

### ProviderController

Tách search/detail/version/install. Click project không cài ngay; load detail và versions trước.

## 5. State machine Launch button

```text
IDLE       → Launch
STARTING   → Pause | Cancel
RUNNING    → Launch disabled / Stop Game tùy thiết kế
PAUSED     → Resume | Cancel
CANCELLING → disabled
FAILED     → Launch
FINISHED   → Launch
```

Không dùng text button làm source of truth; giữ enum state trong controller/view model.

## 6. Progress presenter

Presenter chuyển `ProgressEvent` thành:

- title;
- detail;
- determinate/indeterminate;
- percentage;
- speed;
- current/total;
- terminal state.

Không đặt logic provider trong widget progress.

## 7. First Run Setup

Dùng core để:

- `VersionManifestManager.get()` hoặc defer đến màn hình instance;
- `JavaService.scan()`;
- `SystemMemory.total_physical_memory_mb()`;
- `MemoryAllocationPolicy.normalize()`;
- `GpuPreferenceManager.detect()`;
- `LauncherSettingsManager.save()`.

Java scan và GPU detect chạy worker. Wizard không được đóng băng.

## 8. Account UX

Offline account tạo ngay. Microsoft account login chạy worker, có cancel event. Không hiện token trong UI/log. Account selection chỉ giữ `account_id`; load object mới khi launch.

## 9. Instance creation UX

1. user chọn Minecraft version;
2. chọn loader;
3. core resolve loader version;
4. review settings;
5. task create;
6. refresh library;
7. select returned instance.

## 10. Modpack UX

Hai đường:

- Browse online;
- Import provider package.

Cả hai đều phải có preview → settings review → create/import. Với deferred pack, UI ghi rõ mod sẽ tải lần Launch đầu.

## 11. Manual download UX

Dialog phải hiện:

- provider;
- project name;
- expected file name/size;
- official project/version URL;
- reason;
- button Open Web;
- button Select Files;
- verification result.

Không cung cấp nút “bỏ qua hash”.

## 12. Crash handling

`on_exit` cập nhật:

- runtime badge;
- last exit code;
- crash flag;
- log/crash report links;
- optional diagnostic bundle action.

## 13. Startup recovery

Ngay startup:

- bootstrap;
- reconcile process sessions;
- reconcile instance journals;
- clean invalid partial downloads;
- refresh instance status/health.

## 14. Minimal PySide6 integration

Xem `examples/14_minimal_pyside6_launcher.py`. File này có worker QObject, QThread, progress signal, launch result và exception handling.

## 15. Security checklist

- không log token;
- normalize path;
- không extract ZIP tùy ý;
- dùng core importer/validator;
- không trust provider HTML;
- mở external URL qua browser hệ thống;
- chỉ chấp nhận HTTPS cho direct source;
- verify hash/size;
- redact diagnostic bundles;
- không rehost mod trái license.

## 16. Testing strategy

- unit test controller bằng fake core;
- fake progress events;
- provider clients mock HTTP;
- filesystem tests trong temporary root;
- behavioral tests thay vì assert chuỗi source;
- Windows smoke matrix cho Java, process, DPI và update.
