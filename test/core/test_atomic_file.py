from pathlib import Path

import pytest

from src.core.fs import atomic_file


def test_atomic_write_text_retries_permission_error(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "state.json"
    real_replace = atomic_file.os.replace
    calls = []

    def flaky_replace(source, destination):
        calls.append((Path(source), Path(destination)))
        if len(calls) == 1:
            raise PermissionError("sharing violation")
        return real_replace(source, destination)

    monkeypatch.setattr(atomic_file.os, "replace", flaky_replace)
    monkeypatch.setattr(atomic_file.time, "sleep", lambda _delay: None)

    atomic_file.atomic_write_text(target, '{"ok": true}\n')

    assert target.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert len(calls) == 2
    assert calls[0][0] != target
    assert not calls[0][0].exists()


def test_atomic_write_text_cleanup_is_best_effort(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "state.json"

    monkeypatch.setattr(atomic_file, "replace_with_retry", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("locked")))
    original_unlink = Path.unlink

    def locked_unlink(self, *args, **kwargs):
        if self.suffix == ".tmp":
            raise PermissionError("still locked")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked_unlink)

    with pytest.raises(PermissionError, match="locked"):
        atomic_file.atomic_write_text(target, "payload")
