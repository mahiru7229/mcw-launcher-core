# Progress, Worker Threads, Pause, Resume and Cancel

## Core rules

1. Core APIs are synchronous/blocking.
2. Do not run download, repair, provider search, Java installation or launch on the GUI thread.
3. `on_progress` normally executes in the worker context.
4. Marshal progress and completion back to the main thread.

## Console formatter

```python
from mcw_core import ProgressEvent

def format_progress(event: ProgressEvent) -> str:
    text = f"[{event.stage.value}] {event.message}"
    if event.is_determinate:
        text += f" {event.current}/{event.total} ({event.percentage:.1f}%)"
    if event.bytes_per_second:
        text += f" · {event.bytes_per_second / 1024 / 1024:.2f} MiB/s"
    return text
```

## Avoiding progress spam

Bucket determinate updates by 5–10 percent and deduplicate repeated indeterminate stage/message pairs. Keep detailed per-file events in a debug log rather than the main status line.

## Worker pattern

```python
from concurrent.futures import ThreadPoolExecutor
pool = ThreadPoolExecutor(max_workers=4)
future = pool.submit(lambda: core.launch(request))
```

## PySide6 bridge

```python
from PySide6.QtCore import QObject, Signal

class CoreSignals(QObject):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(object)
```

Connect `on_progress=signals.progress.emit`. Signals safely marshal the event to connected Qt slots.

## Operation lifecycle

Simple calls can let `core.launch()` own the operation lifecycle. A GUI that exposes pause/cancel should begin before dispatch and finish in the worker's `finally` block.

```python
core.operations.begin()
try:
    return core.launch(request)
finally:
    core.operations.finish()
```

Pause is cooperative. It does not suspend the running JVM. Cancel causes checkpoints to raise `DownloadCancelledError`. Once Minecraft is running, use `ProcessSupervisor.stop_instance()` to stop the process.

## Success and terminal states

Treat function return as authoritative success and exceptions as failure/cancel/manual intervention. Progress is telemetry; some legacy producers report a `FINISHED` stage without changing `ProgressState` to `SUCCEEDED`.

## `on_exit`

`launch()` returns once the process is started. `on_exit(GameExitResult)` is invoked later, potentially from a watcher thread. Marshal it to the UI thread.
