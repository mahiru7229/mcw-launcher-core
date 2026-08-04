from pathlib import Path
from mcw_core import CorePaths, MCWCore, InstanceCreateRequest
from mcw_core.api.minecraft.version_manifest_manager import VersionManifestManager

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
versions = VersionManifestManager.get()
print("latest:", VersionManifestManager.latest_version())
for version in versions[:10]:
    print(version.id, version.type)

# Uncomment after choosing a valid version.
# instance = core.instances.create(InstanceCreateRequest(
#     name="Example Fabric",
#     version_id="1.21.1",
#     loader_name="fabric",
#     loader_version="auto",
#     on_progress=print,
# ))
# print(instance)
