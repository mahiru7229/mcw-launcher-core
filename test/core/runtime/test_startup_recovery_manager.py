from types import SimpleNamespace

from src.core.runtime.startup_recovery_manager import StartupRecoveryManager


def test_startup_recovery_runs_all_reconcilers(monkeypatch) -> None:
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.InstanceDeletionManager.process_pending", lambda: ["Old"])
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.InstanceRunLock.reconcile", lambda: ("Stale",))
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.ProcessSupervisor.reconcile", lambda: ("Interrupted",))
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.InstanceOperationJournal.recover_all", lambda: (SimpleNamespace(result="rolled-back"),))
    monkeypatch.setattr(StartupRecoveryManager, "_remove_orphan_staging", staticmethod(lambda: ("orphan",)))
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.download_recovery_manager.reconcile", lambda delete_invalid_parts=True: SimpleNamespace(cleaned_count=2))
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.download_recovery_manager.remove_orphan_parts", lambda: ("cache/file.jar.part",))
    called = []
    monkeypatch.setattr("src.core.runtime.startup_recovery_manager.InstanceManager.reconcile_registry", lambda: called.append("registry"))

    report = StartupRecoveryManager.reconcile()

    assert report.deleted_instances == ("Old",)
    assert report.stale_locks == ("Stale",)
    assert report.interrupted_sessions == ("Interrupted",)
    assert report.orphan_staging_paths == ("orphan",)
    assert report.orphan_partial_paths == ("cache/file.jar.part",)
    assert report.download_journal_entries_cleaned == 2
    assert report.recovered_item_count == 8
    assert called == ["registry"]
