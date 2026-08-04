from pathlib import Path
from mcw_core import CorePaths, MCWCore
from mcw_core.api.system.memory import SystemMemory, MemoryAllocationPolicy
from mcw_core.api.hardware.gpu_preference_manager import GpuPreferenceManager

core = MCWCore(CorePaths.from_root(Path.cwd() / "mcw-data"))
for java in core.java.scan():
    print(java.display_name, java.executable, java.valid)

total = SystemMemory.total_physical_memory_mb()
print("RAM:", MemoryAllocationPolicy.format_mb(total))
print("normalized:", MemoryAllocationPolicy.normalize(1024, 8192, total))
print("GPU:", GpuPreferenceManager.detect())
