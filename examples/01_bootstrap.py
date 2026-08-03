from pathlib import Path
from mcw_core import CorePaths
from mcw_core.api.bootstrap import initialize_application

CorePaths.from_root(Path.cwd() / "mcw-data").apply()
settings = initialize_application(lambda percent, key: print(f"{percent:3d}% {key}"))
print(settings)
