from pathlib import Path
from mcw_core import CorePaths, MCWCore

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
package = Path("example.mrpack")
preview = core.instances.inspect_modpack_package(package)
print(preview)
instance = core.instances.import_modpack_package(
    package,
    on_progress=print,
    settings_override={"min_memory": 2048, "max_memory": 8192},
    instance_name="Imported Example",
)
print(instance)
exported = core.instances.export_modpack(instance.name, Path("portable.mcwpack"), mode="portable", portable_mode="smart", on_progress=print)
print(exported)
