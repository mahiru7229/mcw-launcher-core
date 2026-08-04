from pathlib import Path
from mcw_core import CorePaths, MCWCore, LaunchRequest, ProgressEvent

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))

def progress(event: ProgressEvent) -> None:
    text = f"[{event.stage.value}] {event.message}"
    if event.is_determinate:
        text += f" {event.percentage:.1f}%"
    print(text)

def exited(result) -> None:
    print("game exited:", result.to_dict())

result = core.launch(LaunchRequest(
    instance="My Instance",
    offline_username="Player",
    on_progress=progress,
    on_exit=exited,
))
print("process started:", result.as_dict())
