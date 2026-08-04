from pathlib import Path
import importlib.metadata
import mcw_core
from mcw_core import CorePaths, MCWCore

print("distribution:", importlib.metadata.version("mcw-core"))
print("runtime:", mcw_core.__version__)
core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
print("root:", core.paths.root)
print("instances:", len(core.instances.list()))
