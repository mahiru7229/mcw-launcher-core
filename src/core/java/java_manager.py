from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource
from pathlib import Path

from src.core.progress.progress_reporter import ProgressReporter
from src.models.progress.progress_stage import ProgressStage
import subprocess
import re
import os
import shutil
try:
    import winreg
except ImportError:  # Windows-only standard library module
    winreg = None


class JavaManager:
    JAVA_VENDOR_DIRECTORIES = (
    "Java",
    "Eclipse Adoptium",
    "Microsoft",
    "Amazon Corretto",
    "BellSoft",
    "Zulu",
    "Azul Systems",
    )
    JAVA_REGISTRY_KEYS = (
    r"SOFTWARE\JavaSoft\Java Runtime Environment",
    r"SOFTWARE\JavaSoft\JRE",
    r"SOFTWARE\JavaSoft\Java Development Kit",
    r"SOFTWARE\JavaSoft\JDK",
    )


    @staticmethod
    def _creation_flags() -> int:
        if JavaManager._is_windows():
            return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))

        return 0


    @staticmethod
    def find_installation(reporter: ProgressReporter | None = None) -> list[JavaInstallation]:
        return JavaManager._remove_duplicates(JavaManager.find_installation_candidates(reporter))

    @staticmethod
    def find_installation_candidates(reporter: ProgressReporter | None = None) -> list[JavaInstallation]:
        """Return every usable Java installation, deduplicated by executable path.

        ``find_installation`` intentionally keeps the historic one-runtime-per-major
        contract. Recovery needs a wider candidate pool so a broken Java 17 can be
        replaced by another Java 17 installation without changing existing callers.
        """
        javas: list[JavaInstallation] = []
        sources = (
            ("java.scan.source.java_home", JavaManager._scan_java_home),
            ("java.scan.source.path", JavaManager._scan_path),
            ("java.scan.source.program_files", JavaManager._scan_program_files),
            ("java.scan.source.registry", JavaManager._scan_registry),
            ("java.scan.source.managed", JavaManager._scan_managed_runtimes),
        )
        for message, scanner in sources:
            if reporter is not None:
                reporter.status(ProgressStage.SELECTING_JAVA, message)
            javas.extend(scanner())

        if reporter is not None:
            reporter.status(ProgressStage.SELECTING_JAVA, "java.scan.sources_completed")
        return JavaManager._remove_duplicate_paths(javas)

    @staticmethod
    def _scan_managed_runtimes() -> list[JavaInstallation]:
        return JavaManager._scan_source(JavaManager._get_java_in_managed_runtimes(), JavaSource.MINECRAFT_RUNTIME)

    @staticmethod
    def _get_java_in_managed_runtimes() -> list[Path]:
        from src.core.java.managed_java_repository import ManagedJavaRepository

        root = ManagedJavaRepository.root()
        results: list[Path] = []
        try:
            directories = tuple(root.iterdir())
        except OSError:
            return results
        for directory in directories:
            executable = directory / "bin" / JavaManager._java_executable_names()[0]
            if directory.is_dir() and executable.is_file():
                results.append(executable)
        return results

    @staticmethod
    def _scan_registry() -> list[JavaInstallation]:
        return JavaManager._scan_source(
            JavaManager._get_java_in_registry(),
            JavaSource.REGISTRY,
        )
    @staticmethod
    def _get_java_in_registry() -> list[Path]:
        if not JavaManager._is_windows() or winreg is None:
            return []
        java_paths: list[Path] = []

        registry_views = (
            winreg.KEY_WOW64_64KEY,
            winreg.KEY_WOW64_32KEY,
        )

        for key_path in JavaManager.JAVA_REGISTRY_KEYS:
            for registry_view in registry_views:
                java_paths.extend(
                    JavaManager._get_java_homes_from_registry_key(
                        winreg.HKEY_LOCAL_MACHINE,
                        key_path,
                        registry_view,
                    )
                )

        return java_paths

    @staticmethod
    def _get_java_homes_from_registry_key(root: int, key_path: str, access: int,) -> list[Path]:
        java_homes: list[Path] = []
        try:
            with winreg.OpenKey(root, key_path, 0,winreg.KEY_READ | access,
            ) as key:
                index = 0
                while True:
                    try:
                        version_name = winreg.EnumKey(key, index)
                        index += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, version_name) as version_key:
                            java_home, _ = winreg.QueryValueEx(
                                version_key,
                                "JavaHome",
                            )
                    except (FileNotFoundError, OSError):
                        continue
                    java_path = Path(java_home) / "bin" / JavaManager._java_executable_names()[0]
                    if java_path.is_file():
                        java_homes.append(java_path)
        except (FileNotFoundError, PermissionError, OSError):
            return []

        return java_homes

    @staticmethod
    def _get_program_files_dirs() -> list[Path]:
        if not JavaManager._is_windows():
            return []
        directories: list[Path] = []
        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files:
            directories.append(Path(program_files))
        if program_files_x86:
            directories.append(Path(program_files_x86))
        return directories

    @staticmethod
    def _get_java_in_program_files() -> list[Path]:
        java_paths: list[Path] = []
        for program_files_dir in JavaManager._get_program_files_dirs():
            for vendor_dir_name in JavaManager.JAVA_VENDOR_DIRECTORIES:
                vendor_dir = program_files_dir / vendor_dir_name
                if not vendor_dir.is_dir():
                    continue
                for java_home in vendor_dir.iterdir():
                    java_executable = java_home / "bin" / JavaManager._java_executable_names()[0]
                    if java_executable.is_file():
                        java_paths.append(java_executable)
        return java_paths
    @staticmethod
    def _scan_program_files() -> list[JavaInstallation]:
        return JavaManager._scan_source(
            JavaManager._get_java_in_program_files(),
            JavaSource.PROGRAM_FILES
        )
    @staticmethod
    def _scan_source(paths:list[Path] | None, source:JavaSource) -> list[JavaInstallation]:
        if not paths:
            return []
        javas:list[JavaInstallation]= []
        for java_path in paths:
    
            if not java_path:
                continue

            java_path_version = JavaManager._get_major_version(java_path)
            if java_path_version is None:
                continue

            javas.append(JavaInstallation(
            version=java_path_version,
            executable = java_path,
            source=source)
        )
        return javas




    
    @staticmethod
    def _get_java_in_java_home() -> list[Path] | None:
        java_home = os.environ.get("JAVA_HOME")
        if not java_home:
            return None
        home_path = Path(java_home)
        candidates = [
            directory / executable
            for directory in (home_path / "bin", home_path)
            for executable in JavaManager._java_executable_names()
        ]
        for java_path in candidates:
            if java_path.is_file():
                return [java_path]
        return None
    @staticmethod
    def _get_java_in_path() -> list[Path] | None:
        if JavaManager._is_windows():
            try:
                result = subprocess.run(
                    ["where", "java"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=8,
                    creationflags=JavaManager._creation_flags(),
                )
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                FileNotFoundError,
                PermissionError,
                OSError,
            ):
                return None
            java_paths: list[Path] = []
            for raw_path in result.stdout.splitlines():
                raw_path = raw_path.strip()
                if not raw_path:
                    continue
                java_path = JavaManager.normalize_executable(Path(raw_path))
                if java_path not in java_paths:
                    java_paths.append(java_path)
            return java_paths or None

        java_paths: list[Path] = []
        for command_name in ("java",):
            resolved = shutil.which(command_name)
            if not resolved:
                continue
            java_path = JavaManager.normalize_executable(Path(resolved))
            if java_path.is_file() and java_path not in java_paths:
                java_paths.append(java_path)
        return java_paths or None

    @staticmethod
    def get_major_version(java_path: Path) -> int | None:
        return JavaManager._get_major_version(java_path)

    @staticmethod
    def normalize_executable(java_path: Path) -> Path:
        path = Path(java_path)
        if JavaManager._is_windows() and path.name.casefold() == "java.exe":
            javaw_path = path.with_name("javaw.exe")
            if javaw_path.is_file():
                return javaw_path
        return path

    @staticmethod
    def _get_major_version(
        java_path: Path
    ) -> int | None:
        probe_path = JavaManager._version_probe_executable(java_path)
        try:
            result = subprocess.run(
                [str(probe_path), "-version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=8,
                creationflags=JavaManager._creation_flags(),
            )

        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            FileNotFoundError,
            PermissionError,
            OSError,
        ):
            return None

        output = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()

        if not output:
            return None

        first_line = output.splitlines()[0]

        match = re.search(
            r'version "(?:1\.)?(\d+)',
            first_line,
        )

        if match is None:
            return None

        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _version_probe_executable(java_path: Path) -> Path:
        path = Path(java_path)
        if path.name.casefold() == "javaw.exe":
            console_path = path.with_name("java.exe")
            if console_path.is_file():
                return console_path
        return path

    @staticmethod
    def _is_windows() -> bool:
        return os.name == "nt"

    @staticmethod
    def _java_executable_names() -> tuple[str, ...]:
        if JavaManager._is_windows():
            return ("javaw.exe", "java.exe")
        return ("java",)


    @staticmethod
    def _remove_duplicate_paths(javas: list[JavaInstallation]) -> list[JavaInstallation]:
        unique: list[JavaInstallation] = []
        seen: set[str] = set()
        for java in javas:
            try:
                key = os.path.normcase(str(java.executable.resolve(strict=False)))
            except OSError:
                key = os.path.normcase(str(java.executable))
            if key in seen:
                continue
            seen.add(key)
            unique.append(java)
        return unique

    @staticmethod
    def _remove_duplicates(javas: list[JavaInstallation]) -> list[JavaInstallation]:
        source_priority = {
            JavaSource.MINECRAFT_RUNTIME: 4,
            JavaSource.PROGRAM_FILES: 3,
            JavaSource.JAVA_HOME: 2,
            JavaSource.REGISTRY: 1,
            JavaSource.PATH: 0,
        }

        unique: dict[int, JavaInstallation] = {}
        for java in javas:
            current = unique.get(java.version)
            if current is None:
                unique[java.version] = java
                continue
            current_priority = source_priority.get(current.source, -1)
            new_priority = source_priority.get(java.source, -1)
            if new_priority > current_priority:
                unique[java.version] = java
        return list(unique.values())
    


    @staticmethod
    def _scan_path() -> list[JavaInstallation]:
        
        return JavaManager._scan_source(JavaManager._get_java_in_path(), JavaSource.PATH)



    @staticmethod
    def _scan_java_home() -> list[JavaInstallation]:
        return JavaManager._scan_source(JavaManager._get_java_in_java_home(), JavaSource.JAVA_HOME)
