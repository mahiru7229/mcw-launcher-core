from pathlib import Path
from mcw_core import CorePaths, MCWCore
from mcw_core.api.content.installed_content_library import InstalledContentLibraryManager
from mcw_core.api.content.content_pack_manager import ContentPackManager

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
instance = core.instances.load("My Instance")
# ContentPackManager.import_local(instance, "resourcepack", Path("resource-pack.zip"))
library = InstalledContentLibraryManager.scan(instance)
for item in library.items:
    print(item.item_id, item.content_type, item.name, item.provider, item.status)
