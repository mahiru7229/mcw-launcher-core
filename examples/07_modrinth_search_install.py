from pathlib import Path
from mcw_core import CorePaths, MCWCore
from mcw_core.api.modrinth.modrinth_client import ModrinthClient
from mcw_core.api.modrinth.modrinth_mod_installer import ModrinthModInstaller
from mcw_core.api.progress.progress_reporter import ProgressReporter

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
instance = core.instances.load("My Fabric Instance")
search = ModrinthClient.search_projects("mod", "sodium", instance.version_id, "fabric", "downloads")
project = search.projects[0]
versions = ModrinthClient.list_project_versions(project.project_id, "fabric", instance.version_id, ("release",))
result = ModrinthModInstaller.install(instance, versions[0].version_id, install_dependencies=True, reporter=ProgressReporter(print))
print(result)
