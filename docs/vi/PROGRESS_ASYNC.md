# Progress, worker thread, Pause, Resume và Cancel

## Quy tắc quan trọng

1. Core API là synchronous/blocking.
2. Không gọi download, repair, Java scan/install, provider search hoặc launch trực tiếp từ GUI thread.
3. `on_progress` thường chạy trong worker thread.
4. Callback chỉ nên tạo dữ liệu nhẹ hoặc emit signal thread-safe.
5. UI thread mới được sửa widget.

## Format progress cho console

```python
from mcw_core import ProgressEvent, ProgressUnit

def format_progress(event: ProgressEvent) -> str:
    label = f"[{event.stage.value}] {event.message}"
    if event.is_determinate:
        label += f" {event.current}/{event.total} ({event.percentage:.1f}%)"
    if event.bytes_per_second:
        label += f" · {event.bytes_per_second / 1024 / 1024:.2f} MiB/s"
    if event.detail:
        label += f"\n{event.detail}"
    return label
```

## Coalesce để không spam UI/log

```python
class ProgressCoalescer:
    def __init__(self) -> None:
        self.last_key = None

    def accept(self, event) -> bool:
        if not event.is_determinate:
            key = (event.stage.value, event.message, None)
        else:
            percent = int(event.percentage or 0)
            bucket = 100 if percent >= 100 else percent // 5 * 5
            key = (event.stage.value, bucket)
        if key == self.last_key:
            return False
        self.last_key = key
        return True
```

## ThreadPoolExecutor pattern

```python
from concurrent.futures import ThreadPoolExecutor

pool = ThreadPoolExecutor(max_workers=4)
future = pool.submit(lambda: core.launch(request))
future.add_done_callback(on_done)
```

Không update widget trong `on_done` nếu callback đang chạy ở worker thread.

## PySide6 signal bridge

```python
from PySide6.QtCore import QObject, Signal

class CoreSignals(QObject):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(object)

signals = CoreSignals()
request = LaunchRequest(instance=name, account=account, on_progress=signals.progress.emit)
```

## Operation lifecycle

### Call đơn giản

Nếu không cần pause/cancel từ bên ngoài, gọi `core.launch()` trực tiếp. Facade sẽ begin/finish operation nếu chưa có operation active.

### UI controlled

```python
core.operations.begin()
try:
    result = core.launch(request)
finally:
    core.operations.finish()
```

UI buttons:

```python
pause_button.clicked.connect(core.operations.pause)
resume_button.clicked.connect(core.operations.resume)
cancel_button.clicked.connect(core.operations.cancel)
```

### State

```python
state = core.operations.state
print(state.active, state.paused, state.cancel_requested)
```

## Pause semantics

Pause không suspend Python thread bằng force và không suspend JVM. Nó đặt cooperative state. Downloader gọi checkpoint và chờ condition. Vì vậy:

- pause phản hồi tốt trong download/retry/delay;
- một system call ngắn đang chạy có thể hoàn thành trước khi pause có hiệu lực;
- sau `LAUNCHING`, pause không phải nút pause game.

## Cancel semantics

Cancel làm checkpoint raise `DownloadCancelledError`. Luôn cleanup trong `finally`.

```python
try:
    operation()
except DownloadCancelledError:
    status = "cancelled"
finally:
    core.operations.finish()
```

## Terminal state

Không giả định mọi progress producer dùng `ProgressState.SUCCEEDED`. Với operation cấp cao:

- function return = success;
- exception = failure/cancel/manual intervention;
- progress = telemetry cho UI.

## Mapping sang UI

| Core | UI gợi ý |
|---|---|
| `PREPARING` | indeterminate |
| `DOWNLOADING_*` + bytes | progress + speed |
| `DOWNLOADING_MODS` + files | file count + aggregate speed |
| `INSTALLING_*` | steps hoặc indeterminate |
| `LAUNCHING` | disable pause nếu không còn checkpoint hữu ích |
| return | success state |
| cancellation exception | cancelled state |
| other exception | failed state |

## on_exit

`on_exit` xảy ra sau khi `launch()` đã return. Callback có thể đến từ runtime watcher thread. Hãy emit signal về GUI thread.
