# MCW Core v1.3.0-beta.2

## Fix: complete instance deletion after game exit

MCW Core **v1.3.0-beta.2** fixes a race between `InstanceDeletionManager` and `GameRuntimeManager` post-exit processing.

Previously, deleting an instance immediately after a game session could remove the instance root successfully, then the runtime watcher could wake up afterwards and recreate `crash-reports/` while checking for a crash report and recreate `.mcw/runtime-history.json` while recording the exit result.

Beta 2 now:

- tracks runtime watcher threads per instance;
- waits for all runtime exit processing for that instance before deleting the root;
- queues deletion and reports the condition if finalization does not complete within the safe timeout;
- keeps the registry entry until deletion truly succeeds;
- preserves all v1.3.0-beta.1 Shared Storage, ContentStore, Provider API Cache, and Legacy Storage behavior unchanged.

Regression tests cover the runtime-finalization race and verify that `.mcw`, `crash-reports`, mods, and the instance root are all gone after successful deletion.

## Version metadata

- Runtime: `1.3.0-beta.2`
- Distribution: `1.3.0b2`
- Update channel: `beta`
