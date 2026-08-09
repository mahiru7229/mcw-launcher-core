from __future__ import annotations

from pathlib import Path
import os
import shutil


def to_extended_windows_path(value: str) -> str:
    path = str(value)
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def native_filesystem_path(path: Path | str) -> str:
    value = os.path.abspath(os.fspath(path))
    if os.name != "nt":
        return value
    return to_extended_windows_path(value)


def make_directory(path: Path | str) -> None:
    os.makedirs(native_filesystem_path(path), exist_ok=True)


def open_file(path: Path | str, mode: str):
    return open(native_filesystem_path(path), mode)


def copy_tree(source: Path | str, destination: Path | str) -> None:
    shutil.copytree(native_filesystem_path(source), native_filesystem_path(destination), dirs_exist_ok=True)


def move_path(source: Path | str, destination: Path | str) -> None:
    shutil.move(native_filesystem_path(source), native_filesystem_path(destination))


def is_file(path: Path | str) -> bool:
    return os.path.isfile(native_filesystem_path(path))


def stat_path(path: Path | str):
    return os.stat(native_filesystem_path(path))


def replace_path(source: Path | str, destination: Path | str) -> None:
    os.replace(native_filesystem_path(source), native_filesystem_path(destination))


def unlink_file(path: Path | str, missing_ok: bool = True) -> None:
    try:
        os.unlink(native_filesystem_path(path))
    except FileNotFoundError:
        if not missing_ok:
            raise


def remove_tree(path: Path | str, ignore_errors: bool = False) -> None:
    shutil.rmtree(native_filesystem_path(path), ignore_errors=ignore_errors)
