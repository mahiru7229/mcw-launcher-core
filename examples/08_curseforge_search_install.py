from pathlib import Path
from mcw_core import CorePaths, MCWCore
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient
from mcw_core.api.curseforge.curseforge_mod_installer import CurseForgeModInstaller
from mcw_core.api.progress.progress_reporter import ProgressReporter

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
instance = core.instances.load("My Forge Instance")
if not CurseForgeClient.is_available():
    raise RuntimeError("CurseForge gateway is unavailable")
search = CurseForgeClient.search_projects("mod", "jei", instance.version_id, "forge")
project = search.projects[0]
files = CurseForgeClient.list_files(project.project_id, instance.version_id, "forge", ("release",))
result = CurseForgeModInstaller.install(instance, project.project_id, files[0].file_id, reporter=ProgressReporter(print))
print(result)
