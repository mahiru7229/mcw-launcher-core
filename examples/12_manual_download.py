from pathlib import Path
from mcw_core import CorePaths, MCWCore, LaunchRequest
from mcw_core.api.package.portable_content_manager import PortableManualDownloadRequired

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
try:
    core.launch(LaunchRequest(instance="Portable Pack", offline_username="Player"))
except PortableManualDownloadRequired as error:
    for req in error.requirements:
        print(req.project_name, req.file_name, req.project_url, req.reason)
    selected = [Path(value) for value in input("Downloaded file paths, separated by ;: ").split(';') if value.strip()]
    result = core.instances.install_portable_manual_files(error.instance.name, error.requirements, selected)
    print(result)
