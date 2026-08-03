from pathlib import Path
from mcw_core import CorePaths, MCWCore
from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager
from mcw_core.api.repair.repair_service import RepairService
from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
instance = core.instances.load("My Instance")
backup = InstanceBackupManager.create(instance, scope="full", reason="manual")
print(backup)
report = RepairService.scan(instance, mode="quick", on_progress=print)
plan = RepairService.build_plan(report)
print(report.to_dict())
if plan.can_repair:
    print(RepairService.repair(instance, plan, on_progress=print).to_dict())
DiagnosticsManager.write_bundle(Path("diagnostics.zip"), "1.0.0", settings={}, activity_log="")
