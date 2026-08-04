from pathlib import Path
from threading import Thread
from time import sleep
from mcw_core import CorePaths, MCWCore, LaunchRequest, is_download_cancelled

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))

def worker() -> None:
    core.operations.begin()
    try:
        result = core.launch(LaunchRequest(instance="My Instance", offline_username="Player", on_progress=print))
        print(result)
    except Exception as error:
        if is_download_cancelled(error):
            print("cancelled")
        else:
            raise
    finally:
        core.operations.finish()

thread = Thread(target=worker, daemon=True)
thread.start()
sleep(2)
core.operations.pause()
sleep(1)
core.operations.resume()
# core.operations.cancel()
thread.join()
