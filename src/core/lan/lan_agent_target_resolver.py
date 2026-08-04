from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct
import zipfile

from src.core.fs.paths import Paths
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.core.network.httpx_downloader import HttpDownloader
from src.core.progress.progress_reporter import ProgressReporter
from src.models.instance.instance import Instance
from src.models.minecraft.download import DownloadClient
from src.models.minecraft.version import Version
from src.models.progress.progress_stage import ProgressStage


@dataclass(frozen=True, slots=True)
class LanAgentTarget:
    namespace: str
    class_name: str
    method_name: str

    @property
    def encoded(self) -> str:
        return f"{self.class_name}#{self.method_name}"


@dataclass(frozen=True, slots=True)
class LanAgentTargetResolution:
    game_version: str
    loader: str
    targets: tuple[LanAgentTarget, ...]
    warnings: tuple[str, ...] = ()

    @property
    def encoded_targets(self) -> str:
        return ";".join(target.encoded for target in self.targets)


class LanAgentTargetResolver:
    """Resolve the LAN authentication setter across modern Minecraft mappings.

    Minecraft 1.17 through 25.x is obfuscated in production. Fabric remaps the
    game to intermediary names, Forge runs the SRG-remapped client artifact,
    and Vanilla uses the official namespace. Minecraft 26.1+ exposes named
    runtime classes, so named aliases remain candidates for every version.
    """

    MIN_SUPPORTED_VERSION = (1, 17, 0)
    NAMED_CLASS = "net/minecraft/server/MinecraftServer"
    NAMED_METHODS = ("setUsesAuthentication", "setOnlineMode")
    TARGET_DESCRIPTOR = "(Z)V"

    @classmethod
    def resolve(cls, version: Version, instance: Instance, reporter: ProgressReporter | None = None) -> LanAgentTargetResolution:
        game_version = str(getattr(instance, "version_id", "") or getattr(version, "id", "")).strip()
        loader, _ = ModLoaderManager.normalize(getattr(instance, "mod_loader", (ModLoaderManager.VANILLA, "-1")))
        parsed_version = cls._parse_release_version(game_version)

        if parsed_version is not None and parsed_version < cls.MIN_SUPPORTED_VERSION:
            return LanAgentTargetResolution(
                game_version=game_version,
                loader=loader,
                targets=(),
                warnings=("MCW LAN Agent supports Minecraft 1.17 or newer.",),
            )

        preferred_named_methods = cls.NAMED_METHODS if parsed_version is None or parsed_version >= (26, 1, 0) else tuple(reversed(cls.NAMED_METHODS))
        targets: list[LanAgentTarget] = [
            LanAgentTarget("named", cls.NAMED_CLASS, method_name) for method_name in preferred_named_methods
        ]
        warnings: list[str] = []

        official_target: LanAgentTarget | None = None
        try:
            mapping_path = cls._ensure_client_mappings(version, game_version, reporter)
            if mapping_path is not None:
                official_target = cls._parse_mojang_client_mappings(mapping_path)
                if official_target is not None:
                    targets.append(official_target)
                else:
                    warnings.append("The Mojang client mappings did not contain the LAN authentication setter.")
            elif parsed_version is not None and parsed_version < (26, 1, 0):
                warnings.append("This version metadata does not expose Mojang client mappings; only named runtime detection is available.")
        except Exception as error:
            warnings.append(f"Mojang mapping resolution failed safely: {type(error).__name__}: {error}")

        if loader in {ModLoaderManager.FABRIC, ModLoaderManager.QUILT} and official_target is not None:
            try:
                mapping_target = cls._resolve_fabric_family_target(version, loader, official_target)
                if mapping_target is None:
                    mapping_label = "intermediary or Hashed" if loader == ModLoaderManager.QUILT else "intermediary"
                    warnings.append(f"{loader.title()} {mapping_label} mappings did not contain the LAN authentication setter or were not downloaded.")
                else:
                    targets.insert(0, mapping_target)
            except Exception as error:
                warnings.append(f"{loader.title()} mapping resolution failed safely: {type(error).__name__}: {error}")

        if loader in ModLoaderManager.FORGE_FAMILY and official_target is not None:
            loader_title = "NeoForge" if loader == ModLoaderManager.NEOFORGE else "Forge"
            try:
                forge_target = cls._resolve_forge_srg_target(version, game_version, official_target)
                if forge_target is None:
                    warnings.append(f"{loader_title} SRG runtime artifacts did not contain the LAN authentication setter; named and official targets remain available.")
                else:
                    namespace = "neoforge-srg" if loader == ModLoaderManager.NEOFORGE else "forge-srg"
                    targets.insert(0, LanAgentTarget(namespace, forge_target.class_name, forge_target.method_name))
            except Exception as error:
                warnings.append(f"{loader_title} SRG mapping resolution failed safely: {type(error).__name__}: {error}")

        return LanAgentTargetResolution(
            game_version=game_version,
            loader=loader,
            targets=cls._deduplicate(targets),
            warnings=tuple(warnings),
        )

    @classmethod
    def _ensure_client_mappings(cls, version: Version, game_version: str, reporter: ProgressReporter | None) -> Path | None:
        downloads = getattr(version, "downloads", {}) or {}
        mapping_data = downloads.get("client_mappings") if isinstance(downloads, dict) else None
        if not isinstance(mapping_data, dict):
            raw_downloads = (getattr(version, "raw_json", {}) or {}).get("downloads", {})
            mapping_data = raw_downloads.get("client_mappings") if isinstance(raw_downloads, dict) else None
        if not isinstance(mapping_data, dict):
            return None

        url = str(mapping_data.get("url", "")).strip()
        sha1 = str(mapping_data.get("sha1", "")).strip().lower()
        try:
            size = int(mapping_data.get("size", 0) or 0)
        except (TypeError, ValueError):
            size = 0
        if not url or len(sha1) != 40:
            return None

        safe_version = re.sub(r"[^A-Za-z0-9._-]+", "-", game_version).strip("-") or "unknown"
        destination = Paths.CACHE_ROOT / "runtime" / "agents" / "mcw-lan-agent" / "mappings" / safe_version / "client.txt"
        info = DownloadClient(url=url, sha1=sha1, size=size)
        return HttpDownloader.download(
            download_info=info,
            path=destination,
            max_retry=3,
            reporter=reporter,
            progress_stage=ProgressStage.DOWNLOADING_LIBRARIES,
            progress_message=f"Downloading Minecraft {game_version} mappings...",
        )

    @classmethod
    def _parse_mojang_client_mappings(cls, path: Path) -> LanAgentTarget | None:
        current_class_matches = False
        official_class = ""

        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue

            if not raw_line[:1].isspace():
                current_class_matches = False
                class_line = raw_line.strip()
                if not class_line.endswith(":") or " -> " not in class_line:
                    continue
                named_class, mapped_class = class_line[:-1].split(" -> ", 1)
                if named_class.strip() == cls.NAMED_CLASS.replace("/", "."):
                    official_class = mapped_class.strip().replace(".", "/")
                    current_class_matches = True
                continue

            if not current_class_matches or " -> " not in raw_line:
                continue

            left, mapped_name = raw_line.strip().rsplit(" -> ", 1)
            left = re.sub(r"^(?:\d+:\d+:)+", "", left)
            left = re.sub(r":\d+:\d+$", "", left)
            match = re.fullmatch(r"(?P<return>\S+)\s+(?P<name>[^\s(]+)\((?P<args>[^)]*)\)", left)
            if match is None:
                continue
            if match.group("return") != "void" or match.group("name") not in cls.NAMED_METHODS:
                continue
            arguments = tuple(part.strip() for part in match.group("args").split(",") if part.strip())
            if arguments != ("boolean",):
                continue
            return LanAgentTarget("official", official_class, mapped_name.strip())

        return None

    @classmethod
    def _resolve_fabric_family_target(cls, version: Version, loader: str, official_target: LanAgentTarget) -> LanAgentTarget | None:
        intermediary_path = cls._find_intermediary_jar(version)
        if intermediary_path is not None:
            target = cls._parse_intermediary_mappings(intermediary_path, official_target)
            if target is not None:
                return target
        if loader == ModLoaderManager.QUILT:
            hashed_path = cls._find_quilt_hashed_jar(version)
            if hashed_path is not None:
                return cls._parse_quilt_hashed_mappings(hashed_path, official_target)
        return None

    @classmethod
    def _find_intermediary_jar(cls, version: Version) -> Path | None:
        return cls._find_mapping_jar(version, "net.fabricmc:intermediary:")

    @classmethod
    def _find_quilt_hashed_jar(cls, version: Version) -> Path | None:
        return cls._find_mapping_jar(version, "org.quiltmc:hashed:")

    @classmethod
    def _find_mapping_jar(cls, version: Version, coordinate_prefix: str) -> Path | None:
        for library in getattr(version, "libraries", []) or []:
            if not isinstance(library, dict):
                continue
            coordinate = str(library.get("name", "")).strip()
            if not coordinate.startswith(coordinate_prefix):
                continue
            artifact = library.get("downloads", {}).get("artifact", {})
            if isinstance(artifact, dict) and artifact.get("path"):
                candidate = Paths.libraries() / Path(str(artifact["path"]))
                if candidate.is_file():
                    return candidate

            parts = coordinate.split(":")
            if len(parts) >= 3:
                group, artifact_name, artifact_version = parts[:3]
                classifier = parts[3] if len(parts) > 3 else ""
                suffix = f"-{classifier}" if classifier else ""
                filename = f"{artifact_name}-{artifact_version}{suffix}.jar"
                candidate = Paths.libraries() / Path(*group.split("."), artifact_name, artifact_version, filename)
                if candidate.is_file():
                    return candidate
        return None

    @classmethod
    def _resolve_forge_srg_target(cls, version: Version, game_version: str, official_target: LanAgentTarget) -> LanAgentTarget | None:
        artifacts = cls._find_forge_runtime_jars(version, game_version)
        if artifacts is None:
            return None

        slim_jar, srg_jar = artifacts
        slim_methods = cls._read_class_methods(slim_jar, official_target.class_name)
        srg_methods = cls._read_class_methods(srg_jar, official_target.class_name)
        if len(slim_methods) != len(srg_methods):
            raise RuntimeError("Forge slim and SRG MinecraftServer method tables have different lengths.")

        matching_indexes = [
            index
            for index, method in enumerate(slim_methods)
            if method == (official_target.method_name, cls.TARGET_DESCRIPTOR)
        ]
        if len(matching_indexes) != 1:
            return None

        index = matching_indexes[0]
        srg_name, srg_descriptor = srg_methods[index]
        if srg_descriptor != cls.TARGET_DESCRIPTOR or not srg_name:
            return None
        return LanAgentTarget("forge-srg", official_target.class_name, srg_name)

    @classmethod
    def _find_forge_runtime_jars(cls, version: Version, game_version: str) -> tuple[Path, Path] | None:
        mcp_version = cls._forge_mcp_version(version)
        minecraft_client_root = Paths.libraries() / "net" / "minecraft" / "client"
        candidates: list[Path] = []

        if mcp_version:
            candidates.append(minecraft_client_root / f"{game_version}-{mcp_version}")
        if minecraft_client_root.is_dir():
            candidates.extend(
                directory
                for directory in minecraft_client_root.glob(f"{game_version}-*")
                if directory.is_dir() and directory not in candidates
            )

        for directory in candidates:
            prefix = f"client-{directory.name}"
            slim_jar = directory / f"{prefix}-slim.jar"
            srg_jar = directory / f"{prefix}-srg.jar"
            if slim_jar.is_file() and srg_jar.is_file():
                return slim_jar, srg_jar
        return None

    @staticmethod
    def _forge_mcp_version(version: Version) -> str:
        raw_json = getattr(version, "raw_json", {}) or {}
        arguments = getattr(version, "arguments", None) or raw_json.get("arguments", {})
        game_arguments = arguments.get("game", []) if isinstance(arguments, dict) else []
        for flag in ("--fml.neoFormVersion", "--fml.mcpVersion"):
            for index, value in enumerate(game_arguments):
                if value == flag and index + 1 < len(game_arguments):
                    next_value = game_arguments[index + 1]
                    if isinstance(next_value, str):
                        return next_value.strip()
        return ""

    @classmethod
    def _read_class_methods(cls, jar_path: Path, class_name: str) -> list[tuple[str, str]]:
        entry_name = f"{cls._normalize_internal_name(class_name)}.class"
        with zipfile.ZipFile(jar_path) as archive:
            payload = archive.read(entry_name)
        return cls._parse_class_method_table(payload)

    @staticmethod
    def _parse_class_method_table(payload: bytes) -> list[tuple[str, str]]:
        view = memoryview(payload)
        offset = 0

        def read_u1() -> int:
            nonlocal offset
            if offset + 1 > len(view):
                raise RuntimeError("Unexpected end of Java class file.")
            value = view[offset]
            offset += 1
            return int(value)

        def read_u2() -> int:
            nonlocal offset
            if offset + 2 > len(view):
                raise RuntimeError("Unexpected end of Java class file.")
            value = struct.unpack_from(">H", view, offset)[0]
            offset += 2
            return value

        def read_u4() -> int:
            nonlocal offset
            if offset + 4 > len(view):
                raise RuntimeError("Unexpected end of Java class file.")
            value = struct.unpack_from(">I", view, offset)[0]
            offset += 4
            return value

        def skip(length: int) -> None:
            nonlocal offset
            if length < 0 or offset + length > len(view):
                raise RuntimeError("Invalid Java class file structure.")
            offset += length

        if read_u4() != 0xCAFEBABE:
            raise RuntimeError("Invalid Java class file magic.")
        skip(4)
        constant_pool_count = read_u2()
        utf8_entries: dict[int, str] = {}
        index = 1
        while index < constant_pool_count:
            tag = read_u1()
            if tag == 1:
                length = read_u2()
                if offset + length > len(view):
                    raise RuntimeError("Invalid Java UTF-8 constant.")
                utf8_entries[index] = bytes(view[offset:offset + length]).decode("utf-8", errors="replace")
                skip(length)
            elif tag in {3, 4}:
                skip(4)
            elif tag in {5, 6}:
                skip(8)
                index += 1
            elif tag in {7, 8, 16, 19, 20}:
                skip(2)
            elif tag in {9, 10, 11, 12, 17, 18}:
                skip(4)
            elif tag == 15:
                skip(3)
            else:
                raise RuntimeError(f"Unsupported Java constant-pool tag: {tag}")
            index += 1

        skip(6)
        interfaces_count = read_u2()
        skip(interfaces_count * 2)

        def skip_members(count: int, collect: bool) -> list[tuple[str, str]]:
            members: list[tuple[str, str]] = []
            for _ in range(count):
                skip(2)
                name_index = read_u2()
                descriptor_index = read_u2()
                attributes_count = read_u2()
                if collect:
                    name = utf8_entries.get(name_index, "")
                    descriptor = utf8_entries.get(descriptor_index, "")
                    members.append((name, descriptor))
                for _ in range(attributes_count):
                    skip(2)
                    skip(read_u4())
            return members

        fields_count = read_u2()
        skip_members(fields_count, False)
        methods_count = read_u2()
        return skip_members(methods_count, True)

    @classmethod
    def _parse_intermediary_mappings(cls, path: Path, official_target: LanAgentTarget) -> LanAgentTarget | None:
        return cls._parse_tiny_mapping_jar(path, official_target, "intermediary", "intermediary")

    @classmethod
    def _parse_quilt_hashed_mappings(cls, path: Path, official_target: LanAgentTarget) -> LanAgentTarget | None:
        return cls._parse_tiny_mapping_jar(path, official_target, "hashed", "quilt-hashed")

    @classmethod
    def _parse_tiny_mapping_jar(cls, path: Path, official_target: LanAgentTarget, target_namespace: str, result_namespace: str) -> LanAgentTarget | None:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read("mappings/mappings.tiny").decode("utf-8", errors="replace")

        lines = payload.splitlines()
        if not lines:
            return None
        header = lines[0].split("\t")
        if header[0] == "v1":
            return cls._parse_tiny_v1(lines, header, official_target, target_namespace, result_namespace)
        if header[0] == "tiny" and len(header) >= 5 and header[1] == "2":
            return cls._parse_tiny_v2(lines, header, official_target, target_namespace, result_namespace)
        raise RuntimeError("Unsupported Tiny mapping format.")

    @classmethod
    def _parse_tiny_v1(cls, lines: list[str], header: list[str], official_target: LanAgentTarget, target_namespace: str = "intermediary", result_namespace: str = "intermediary") -> LanAgentTarget | None:
        namespaces = header[1:]
        try:
            official_index = namespaces.index("official")
            target_index = namespaces.index(target_namespace)
        except ValueError as error:
            raise RuntimeError(f"Mappings are missing the official or {target_namespace} namespace.") from error

        target_class = cls._normalize_internal_name(official_target.class_name)
        target_method = ""
        official_class = cls._normalize_internal_name(official_target.class_name)

        for line in lines[1:]:
            columns = line.split("\t")
            if not columns:
                continue
            if columns[0] == "CLASS" and len(columns) >= 1 + len(namespaces):
                names = columns[1:1 + len(namespaces)]
                if cls._normalize_internal_name(names[official_index]) == official_class:
                    target_class = cls._normalize_internal_name(names[target_index])
            elif columns[0] == "METHOD" and len(columns) >= 3 + len(namespaces):
                owner = cls._normalize_internal_name(columns[1])
                descriptor = columns[2].strip()
                names = columns[3:3 + len(namespaces)]
                if owner == official_class and descriptor == cls.TARGET_DESCRIPTOR and names[official_index].strip() == official_target.method_name:
                    target_method = names[target_index].strip()
            if target_method:
                return LanAgentTarget(result_namespace, target_class, target_method)
        return None

    @classmethod
    def _parse_tiny_v2(cls, lines: list[str], header: list[str], official_target: LanAgentTarget, target_namespace: str = "intermediary", result_namespace: str = "intermediary") -> LanAgentTarget | None:
        namespaces = header[3:]
        try:
            official_index = namespaces.index("official")
            target_index = namespaces.index(target_namespace)
        except ValueError as error:
            raise RuntimeError(f"Mappings are missing the official or {target_namespace} namespace.") from error

        current_official_class = ""
        current_target_class = ""
        for line in lines[1:]:
            stripped = line.lstrip("\t")
            columns = stripped.split("\t")
            if not columns:
                continue
            if not line.startswith("\t") and columns[0] == "c" and len(columns) >= 1 + len(namespaces):
                names = columns[1:1 + len(namespaces)]
                current_official_class = cls._normalize_internal_name(names[official_index])
                current_target_class = cls._normalize_internal_name(names[target_index])
                continue
            if current_official_class != cls._normalize_internal_name(official_target.class_name) or columns[0] != "m" or len(columns) < 2 + len(namespaces):
                continue
            descriptor = columns[1]
            names = columns[2:2 + len(namespaces)]
            if descriptor == cls.TARGET_DESCRIPTOR and names[official_index] == official_target.method_name:
                return LanAgentTarget(result_namespace, current_target_class, names[target_index])
        return None

    @staticmethod
    def _normalize_internal_name(value: str) -> str:
        return str(value or "").strip().replace(".", "/")

    @staticmethod
    def _parse_release_version(value: str) -> tuple[int, int, int] | None:
        match = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)

    @staticmethod
    def _deduplicate(targets: list[LanAgentTarget]) -> tuple[LanAgentTarget, ...]:
        seen: set[tuple[str, str]] = set()
        result: list[LanAgentTarget] = []
        for target in targets:
            key = (target.class_name, target.method_name)
            if key in seen:
                continue
            seen.add(key)
            result.append(target)
        return tuple(result)
