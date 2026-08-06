from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil

from src.core.fs.paths import Paths
from src.core.optifine.optifine_registry import OptiFineRegistry
from src.models.instance.instance import Instance


@dataclass(slots=True)
class OptiFineTransaction:
    instance: Instance
    journal_path: Path
    backup_dir: Path
    payload: dict

    @classmethod
    def begin(cls, instance: Instance) -> "OptiFineTransaction":
        cls.recover(instance)
        journal = Paths.optifine_registry(instance).with_name("optifine-transaction.json")
        backup_dir = journal.with_name("optifine-transaction-backup")
        shutil.rmtree(backup_dir, ignore_errors=True)
        backup_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "state": "prepared",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "files": [],
            "outputs": [],
        }
        transaction = cls(instance, journal, backup_dir, payload)
        paths = [Paths.optifine_registry(instance), instance.instance_dir / ".mcw" / "mod-provenance.json"]
        previous = OptiFineRegistry.state(instance)
        if previous.installed and previous.managed:
            managed = transaction._managed_path(previous.mode, previous.installed_path or previous.profile_path)
            if managed is not None:
                paths.append(managed)
            profile = transaction._managed_path("standalone", previous.profile_path)
            if profile is not None:
                paths.append(profile)
        seen: set[Path] = set()
        for path in paths:
            normalized = path.resolve(strict=False)
            if normalized in seen:
                continue
            seen.add(normalized)
            transaction._backup(path)
        transaction._write_journal()
        return transaction

    @classmethod
    def recover(cls, instance: Instance) -> bool:
        journal = Paths.optifine_registry(instance).with_name("optifine-transaction.json")
        backup_dir = journal.with_name("optifine-transaction-backup")
        if not journal.is_file():
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            return False
        try:
            payload = json.loads(journal.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid journal")
        except (OSError, json.JSONDecodeError, ValueError):
            journal.unlink(missing_ok=True)
            shutil.rmtree(backup_dir, ignore_errors=True)
            return False
        transaction = cls(instance, journal, backup_dir, payload)
        transaction.rollback()
        return True

    def mark_applying(self) -> None:
        self.payload["state"] = "applying"
        self._write_journal()

    def register_output(self, path: Path) -> None:
        normalized = self._require_allowed(path)
        value = str(normalized)
        outputs = self.payload.setdefault("outputs", [])
        if value not in outputs:
            outputs.append(value)
            self._write_journal()

    def commit(self) -> None:
        self.payload["state"] = "committed"
        self._write_journal()
        self.journal_path.unlink(missing_ok=True)
        shutil.rmtree(self.backup_dir, ignore_errors=True)

    def rollback(self) -> None:
        original_paths = {str(item.get("path") or "") for item in self.payload.get("files", []) if isinstance(item, dict)}
        for raw in reversed(self.payload.get("outputs", [])):
            try:
                output = self._require_allowed(Path(str(raw)))
            except (RuntimeError, ValueError):
                continue
            if str(output) not in original_paths:
                output.unlink(missing_ok=True)
        for item in reversed(self.payload.get("files", [])):
            if not isinstance(item, dict):
                continue
            try:
                target = self._require_allowed(Path(str(item.get("path") or "")))
            except (RuntimeError, ValueError):
                continue
            existed = bool(item.get("existed", False))
            backup_name = str(item.get("backup") or "")
            backup = self.backup_dir / backup_name if backup_name else None
            if existed and backup is not None and backup.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + ".rollback")
                shutil.copy2(backup, temporary)
                temporary.replace(target)
            elif not existed:
                target.unlink(missing_ok=True)
        self.journal_path.unlink(missing_ok=True)
        shutil.rmtree(self.backup_dir, ignore_errors=True)

    def _backup(self, path: Path) -> None:
        target = self._require_allowed(path)
        index = len(self.payload["files"])
        existed = target.is_file()
        backup_name = f"{index:03d}.bak" if existed else ""
        if existed:
            shutil.copy2(target, self.backup_dir / backup_name)
        self.payload["files"].append({"path": str(target), "existed": existed, "backup": backup_name})

    def _managed_path(self, mode: str, value: str) -> Path | None:
        raw = str(value or "").strip()
        if mode == "standalone":
            return Paths.optifine_profile(self.instance)
        if mode == "forge_mod" and raw:
            candidate = Path(raw)
            try:
                normalized = self._require_allowed(candidate)
            except RuntimeError:
                return None
            mods = Paths.instance_mods_dir(self.instance).resolve(strict=False)
            if normalized.parent != mods:
                return None
            return normalized
        return None

    def _require_allowed(self, path: Path) -> Path:
        target = Path(path).resolve(strict=False)
        root = self.instance.instance_dir.resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError as error:
            raise RuntimeError(f"OptiFine transaction path escapes the instance directory: {target}") from error
        return target

    def _write_journal(self) -> None:
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal_path.with_suffix(self.journal_path.suffix + ".part")
        temporary.write_text(json.dumps(self.payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.journal_path)
