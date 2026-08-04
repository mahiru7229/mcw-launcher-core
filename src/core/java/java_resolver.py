from pathlib import Path

from src.core.java.java_major_policy import JavaMajorPolicy
from src.core.java.java_manager import JavaManager
from src.core.java.java_provisioner import JavaProvisioner
from src.core.java.java_selector import JavaSelector
from src.core.progress.progress_reporter import ProgressReporter


class JavaResolver:
    @staticmethod
    def resolve(required_major: int, reporter: ProgressReporter | None = None, preferred_path: str | Path | None = None) -> Path:
        managed_major = JavaMajorPolicy.resolve(required_major)
        preferred = str(preferred_path or "").strip()
        if preferred:
            return JavaResolver._validate_preferred(Path(preferred), required_major, managed_major)

        try:
            return JavaSelector.select_java(managed_major)
        except RuntimeError:
            return JavaProvisioner.ensure(managed_major, reporter)

    @staticmethod
    def _validate_preferred(path: Path, required_major: int, managed_major: int) -> Path:
        executable = JavaManager.normalize_executable(path)
        if not executable.is_file():
            raise RuntimeError(f"Java path does not exist: {executable}")

        actual_major = JavaManager.get_major_version(executable)
        if actual_major is None:
            raise RuntimeError(f"Unable to determine the Java version at: {executable}")

        accepted = JavaMajorPolicy.accepted_majors(required_major)
        if actual_major not in accepted:
            expected = " or ".join(f"Java {major}" for major in accepted)
            raise RuntimeError(f"Java {actual_major} is incompatible with this Minecraft runtime. Required: {expected}.")
        return executable
