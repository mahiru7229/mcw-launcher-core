from __future__ import annotations

import os
from pathlib import Path

from src.models.minecraft.version import Version


class ForgeLaunchCommandManager:
    """Validate and normalize JVM arguments required by modern Forge."""

    MODERN_MAIN_CLASS = "cpw.mods.bootstraplauncher.BootstrapLauncher"
    MODULE_PATH_FLAGS = ("-p", "--module-path")
    DEFAULT_IGNORE_LIST = (
        "bootstraplauncher",
        "securejarhandler",
        "asm-commons",
        "asm-util",
        "asm-analysis",
        "asm-tree",
        "asm",
        "JarJarFileSystems",
        "client-extra",
        "mixinextras-neoforge",
        "fmlcore",
        "javafmllanguage",
        "lowcodelanguage",
        "mclanguage",
        "forge-",
        "neoforge-",
    )

    @classmethod
    def prepare(cls, version: Version, jvm_arguments: list[str], client_path: Path | None = None, library_directory: Path | None = None) -> list[str]:
        arguments = [str(value) for value in jvm_arguments]
        if not cls.is_modern_forge(version):
            return arguments

        loader_title = cls._loader_title(version)
        module_path_index, module_path, inline = cls._find_module_path(arguments)
        if module_path_index is None:
            raise RuntimeError(
                f"The {loader_title} launch profile does not define a module path. "
                f"Repair or reinstall {loader_title} for this instance."
            )

        if "${" in module_path:
            raise RuntimeError(
                f"The {loader_title} module path still contains unresolved launcher placeholders. "
                f"Repair or reinstall {loader_title}, then try again."
            )

        entries = cls._module_path_entries(module_path)
        entries = cls._remove_minecraft_version_jars(entries, version, client_path)
        if not entries:
            raise RuntimeError(
                f"The {loader_title} launch profile contains an empty module path after removing "
                f"Minecraft version JARs. Repair or reinstall {loader_title} for this instance."
            )

        missing = [entry for entry in entries if not Path(entry).is_file()]
        if missing:
            preview = "\n".join(f"- {path}" for path in missing[:8])
            remaining = len(missing) - min(len(missing), 8)
            suffix = f"\n- ... and {remaining} more" if remaining > 0 else ""
            raise RuntimeError(
                f"{loader_title} cannot start because required module-path libraries are missing. "
                f"Use Repair {loader_title} and try again.\n"
                f"{preview}{suffix}"
            )

        sanitized_module_path = os.pathsep.join(entries)
        if inline:
            arguments[module_path_index] = f"--module-path={sanitized_module_path}"
            insertion_index = module_path_index + 1
        else:
            arguments[module_path_index] = "--module-path"
            arguments[module_path_index + 1] = sanitized_module_path
            insertion_index = module_path_index + 2

        if not cls._has_all_module_path(arguments):
            arguments[insertion_index:insertion_index] = [
                "--add-modules",
                "ALL-MODULE-PATH",
            ]

        arguments = cls._ensure_ignore_list(arguments, version, client_path)
        if library_directory is not None:
            arguments = cls._ensure_system_property(arguments, "libraryDirectory", str(library_directory))
        return arguments

    @classmethod
    def is_modern_forge(cls, version: Version) -> bool:
        raw = getattr(version, "raw_json", None)
        loader_metadata = cls._loader_metadata(raw)
        return str(getattr(version, "main_class", "")).strip() == cls.MODERN_MAIN_CLASS and loader_metadata is not None

    @staticmethod
    def _loader_metadata(raw: object) -> dict | None:
        if not isinstance(raw, dict):
            return None
        for key in ("neoforge", "forge"):
            metadata = raw.get(key)
            if isinstance(metadata, dict):
                return metadata
        return None

    @staticmethod
    def _loader_title(version: Version) -> str:
        raw = getattr(version, "raw_json", None)
        return "NeoForge" if isinstance(raw, dict) and isinstance(raw.get("neoforge"), dict) else "Forge"

    @classmethod
    def _find_module_path(cls, arguments: list[str]) -> tuple[int | None, str, bool]:
        for index, value in enumerate(arguments):
            if value in cls.MODULE_PATH_FLAGS:
                if index + 1 >= len(arguments):
                    return index, "", False
                return index, str(arguments[index + 1]), False
            if value.startswith("--module-path="):
                return index, value.split("=", 1)[1], True
        return None, "", False

    @staticmethod
    def _module_path_entries(module_path: str) -> list[str]:
        return [value.strip() for value in str(module_path).split(os.pathsep) if value.strip()]

    @classmethod
    def _remove_minecraft_version_jars(cls, entries: list[str], version: Version, client_path: Path | None) -> list[str]:
        return [entry for entry in entries if not cls._is_minecraft_version_jar(entry, version, client_path)]

    @classmethod
    def _is_minecraft_version_jar(cls, entry: str, version: Version, client_path: Path | None) -> bool:
        candidate = str(entry).strip()
        if client_path is not None and cls._same_path(candidate, client_path):
            return True

        normalized = candidate.replace("\\", "/").rstrip("/")
        parts = [part for part in normalized.split("/") if part]
        if len(parts) >= 3 and parts[-3].casefold() == "versions":
            version_directory = parts[-2]
            if parts[-1].casefold() == f"{version_directory}.jar".casefold():
                return True

        raw = getattr(version, "raw_json", None)
        inherited = str(raw.get("inheritsFrom") or "").strip() if isinstance(raw, dict) else ""
        client_names = {Path(client_path).name.casefold()} if client_path is not None else set()
        if inherited:
            client_names.add(f"{inherited}.jar".casefold())
        return bool(client_names and Path(normalized).name.casefold() in client_names and "versions" in {part.casefold() for part in parts})

    @staticmethod
    def _same_path(candidate: str, expected: Path) -> bool:
        try:
            return os.path.normcase(os.path.abspath(candidate)) == os.path.normcase(os.path.abspath(str(expected)))
        except (OSError, ValueError):
            return False

    @classmethod
    def _ensure_ignore_list(cls, arguments: list[str], version: Version, client_path: Path | None) -> list[str]:
        required = list(cls.DEFAULT_IGNORE_LIST)
        if client_path is not None:
            required.append(Path(client_path).name)

        raw = getattr(version, "raw_json", None)
        inherited = str(raw.get("inheritsFrom") or "").strip() if isinstance(raw, dict) else ""
        if inherited:
            required.append(f"{inherited}.jar")

        indices = [index for index, value in enumerate(arguments) if value.startswith("-DignoreList=")]
        values: list[str] = []
        if indices:
            values.extend(item.strip() for item in arguments[indices[0]].split("=", 1)[1].split(",") if item.strip())

        seen = {value.casefold() for value in values}
        for value in required:
            if value and value.casefold() not in seen:
                values.append(value)
                seen.add(value.casefold())

        property_argument = f"-DignoreList={','.join(values)}"
        if indices:
            arguments[indices[0]] = property_argument
            for index in reversed(indices[1:]):
                del arguments[index]
        else:
            arguments.append(property_argument)
        return arguments

    @staticmethod
    def _ensure_system_property(arguments: list[str], name: str, value: str) -> list[str]:
        prefix = f"-D{name}="
        indices = [index for index, argument in enumerate(arguments) if argument.startswith(prefix)]
        property_argument = f"{prefix}{value}"
        if indices:
            arguments[indices[0]] = property_argument
            for index in reversed(indices[1:]):
                del arguments[index]
        else:
            arguments.append(property_argument)
        return arguments

    @staticmethod
    def _has_all_module_path(arguments: list[str]) -> bool:
        for index, value in enumerate(arguments):
            if value == "--add-modules" and index + 1 < len(arguments):
                modules = {item.strip() for item in arguments[index + 1].split(",")}
                if "ALL-MODULE-PATH" in modules:
                    return True
            if value.startswith("--add-modules="):
                modules = {item.strip() for item in value.split("=", 1)[1].split(",")}
                if "ALL-MODULE-PATH" in modules:
                    return True
        return False
