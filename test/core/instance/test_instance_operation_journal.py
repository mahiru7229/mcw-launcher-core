from __future__ import annotations

from pathlib import Path

import pytest

from src.core.fs.paths import Paths
from src.core.instance.instance_operation_journal import InstanceOperationJournal


@pytest.fixture(autouse=True)
def isolate_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(Paths, "INSTANCES_ROOT", tmp_path / "instances")


def test_recovery_removes_interrupted_clone_staging() -> None:
    target = Paths.load_instance_dir("Clone")
    staging = Paths.instance_staging_root() / "clone-staging"
    staging.mkdir(parents=True)
    (staging / "partial.txt").write_text("partial", encoding="utf-8")
    journal = InstanceOperationJournal.begin("clone", "Clone", target_path=target, staging_path=staging)

    records = InstanceOperationJournal.recover_all()

    assert records[0].result == "rolled-back"
    assert not staging.exists()
    assert not journal.path.exists()


def test_recovery_keeps_committed_target_and_removes_journal() -> None:
    target = Paths.load_instance_dir("Imported")
    target.mkdir(parents=True)
    (target / "instance.json").write_text("{}", encoding="utf-8")
    staging = Paths.instance_staging_root() / "import-staging"
    journal = InstanceOperationJournal.begin("import", "Imported", target_path=target, staging_path=staging)
    journal.update("committing")

    records = InstanceOperationJournal.recover_all()

    assert records[0].result == "committed"
    assert target.exists()
    assert not journal.path.exists()


def test_recovery_never_deletes_staging_outside_instances_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    journal = InstanceOperationJournal.begin("clone", "Unsafe", target_path=Paths.load_instance_dir("Unsafe"), staging_path=outside)

    InstanceOperationJournal.recover_all()

    assert marker.exists()
    assert not journal.path.exists()
