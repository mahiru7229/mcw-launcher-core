from src.models.minecraft.version import Version
from pathlib import Path
from src.core.minecraft.library_rule_manager import LibraryRuleManager
import os







class ClasspathBuilder:

    @staticmethod
    def build(version: Version, client_path: Path, libraries_dir: Path) -> str:
        classpath: list[str] = []
        for library in version.libraries:
            if not LibraryRuleManager.is_allowed(library):
                continue
            downloads = library.get("downloads")
            if downloads is None:
                continue

            artifact = downloads.get("artifact")
            if artifact is None:
                continue

            library_path = libraries_dir / Path(artifact["path"])
            classpath.append(str(library_path))
        classpath.append(str(client_path))
        return os.pathsep.join(classpath)