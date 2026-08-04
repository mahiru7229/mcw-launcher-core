from __future__ import annotations

import hashlib
import os
import subprocess
import zipfile
from pathlib import Path


class JavaCommandCompactor:
    WINDOWS_COMMAND_LIMIT = 32_767
    SAFE_WINDOWS_COMMAND_LIMIT = 30_000
    CLASSPATH_FLAGS = ("-cp", "-classpath", "--class-path")

    @classmethod
    def prepare(cls, java: Path, command: list[str], instance_dir: Path, force: bool = False) -> list[str]:
        if not force and (os.name != "nt" or cls._command_length(java, command) < cls.SAFE_WINDOWS_COMMAND_LIMIT):
            return list(command)

        classpath_index = cls._classpath_index(command)
        if classpath_index is None or classpath_index + 1 >= len(command):
            return list(command)

        classpath = str(command[classpath_index + 1])
        if not classpath.strip():
            return list(command)

        classpath_jar = cls._write_classpath_jar(classpath, instance_dir)
        compacted = list(command)
        compacted[classpath_index + 1] = str(classpath_jar)
        return compacted

    @staticmethod
    def _command_length(java: Path, command: list[str]) -> int:
        return len(subprocess.list2cmdline([str(java), *map(str, command)]))

    @classmethod
    def _classpath_index(cls, command: list[str]) -> int | None:
        for index, value in enumerate(command):
            if str(value) in cls.CLASSPATH_FLAGS:
                return index
        return None

    @classmethod
    def _write_classpath_jar(cls, classpath: str, instance_dir: Path) -> Path:
        separator = ";" if os.name == "nt" else os.pathsep
        entries = [entry for entry in classpath.split(separator) if entry]
        if not entries:
            raise RuntimeError("Minecraft classpath is empty and cannot be compacted.")

        normalized = [cls._classpath_uri(entry, instance_dir) for entry in entries]
        digest = hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()[:16]
        launch_dir = instance_dir / ".mcw" / "launch"
        launch_dir.mkdir(parents=True, exist_ok=True)
        target = launch_dir / f"classpath-{digest}.jar"
        if target.is_file() and target.stat().st_size > 0 and zipfile.is_zipfile(target):
            return target

        temporary = target.with_suffix(".jar.tmp")
        manifest = cls._manifest_bytes(normalized)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("META-INF/MANIFEST.MF", manifest)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    @staticmethod
    def _classpath_uri(value: str, instance_dir: Path) -> str:
        path = type(instance_dir)(value)
        if not path.is_absolute():
            path = instance_dir / path
        return path.resolve(strict=False).as_uri()

    @classmethod
    def _manifest_bytes(cls, entries: list[str]) -> bytes:
        logical_lines = [
            "Manifest-Version: 1.0",
            "Created-By: MCW Launcher",
            f"Class-Path: {' '.join(entries)}",
        ]
        physical_lines: list[str] = []
        for line in logical_lines:
            physical_lines.extend(cls._wrap_manifest_line(line))
        return ("\r\n".join(physical_lines) + "\r\n\r\n").encode("utf-8")

    @staticmethod
    def _wrap_manifest_line(value: str) -> list[str]:
        encoded = value.encode("utf-8")
        if len(encoded) <= 70:
            return [value]

        lines: list[str] = []
        remaining = encoded
        first = True
        while remaining:
            limit = 70 if first else 69
            chunk = remaining[:limit]
            remaining = remaining[limit:]
            text = chunk.decode("ascii")
            lines.append(text if first else f" {text}")
            first = False
        return lines
