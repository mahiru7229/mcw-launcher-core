from __future__ import annotations

from collections import defaultdict
import re

from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo
from src.models.mod.mod_issue import ModHealthReport, ModIssue


class ModCompatibilityManager:
    @staticmethod
    def scan(instance: Instance, mods: list[ModInfo] | None = None) -> ModHealthReport:
        mods = list(mods) if mods is not None else ModManager.list_mods(instance)
        enabled = [mod for mod in mods if mod.enabled]
        disabled = [mod for mod in mods if not mod.enabled]
        enabled_by_id: dict[str, list[ModInfo]] = defaultdict(list)
        disabled_by_id: dict[str, list[ModInfo]] = defaultdict(list)

        for mod in enabled:
            enabled_by_id[mod.mod_id.casefold()].append(mod)
        for mod in disabled:
            disabled_by_id[mod.mod_id.casefold()].append(mod)

        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        installed_versions = {mod_id: entries[0].version for mod_id, entries in enabled_by_id.items() if entries}
        installed_versions["minecraft"] = instance.version_id
        if loader_name == ModLoaderManager.FABRIC:
            installed_versions["fabricloader"] = loader_version
        elif loader_name == ModLoaderManager.QUILT:
            installed_versions["quilt_loader"] = loader_version
            installed_versions["quiltloader"] = loader_version
            # Quilt Loader exposes Fabric Loader compatibility for Fabric mods.
            installed_versions["fabricloader"] = loader_version
        elif loader_name == ModLoaderManager.FORGE:
            installed_versions["forge"] = loader_version
            installed_versions["javafml"] = loader_version
            installed_versions["fml"] = loader_version
        elif loader_name == ModLoaderManager.NEOFORGE:
            installed_versions["neoforge"] = loader_version
            # NeoForge-compatible Forge-family mods can retain a legacy
            # mandatory dependency on the virtual ``forge`` runtime. The
            # loader-mismatch check still blocks genuinely Forge-only mods,
            # while provider-approved dual-loader mods such as e4mc can pass
            # their own metadata preflight on a NeoForge instance.
            installed_versions["forge"] = loader_version
            installed_versions["javafml"] = loader_version
            installed_versions["fml"] = loader_version

        issues: list[ModIssue] = []
        ModCompatibilityManager._append_file_issues(mods, issues)
        ModCompatibilityManager._append_loader_issues(loader_name, enabled, issues)
        ModCompatibilityManager._append_duplicate_issues(enabled_by_id, issues)

        for mod in enabled:
            ModCompatibilityManager._append_dependency_issues(mod, enabled_by_id, disabled_by_id, installed_versions, issues)
            ModCompatibilityManager._append_conflict_issues(mod, enabled_by_id, installed_versions, issues)

        issues.sort(key=lambda item: ({"error": 0, "warning": 1, "info": 2}.get(item.severity, 3), item.message.casefold()))
        return ModHealthReport(issues=tuple(issues), enabled_mods=len(enabled), disabled_mods=len(disabled))

    @staticmethod
    def _append_file_issues(mods: list[ModInfo], issues: list[ModIssue]) -> None:
        for mod in mods:
            if mod.status in {"Broken JAR", "Broken metadata", "Not a mod"}:
                issues.append(ModIssue(severity="error", code="invalid-mod", message=f"{mod.name}: {mod.error or mod.status}", mod_ids=(mod.mod_id,)))
            elif mod.enabled and mod.status == "Server only":
                issues.append(ModIssue(severity="warning", code="server-only", message=f"{mod.name} is enabled but declares a server-only environment.", mod_ids=(mod.mod_id,)))

    @staticmethod
    def _append_loader_issues(loader_name: str, mods: list[ModInfo], issues: list[ModIssue]) -> None:
        for mod in mods:
            if mod.loader in {"unknown", "universal", loader_name}:
                continue
            issues.append(
                ModIssue(
                    severity="error",
                    code="loader-mismatch",
                    message=f"{mod.name} is a {mod.loader.title()} mod, but this instance uses {loader_name.title()}.",
                    mod_ids=(mod.mod_id,),
                )
            )

    @staticmethod
    def _append_duplicate_issues(enabled_by_id: dict[str, list[ModInfo]], issues: list[ModIssue]) -> None:
        for mod_id, entries in enabled_by_id.items():
            if mod_id == "unknown" or len(entries) < 2:
                continue
            files = ", ".join(item.file_name for item in entries)
            issues.append(ModIssue(severity="error", code="duplicate-mod-id", message=f"Duplicate enabled mod ID '{mod_id}': {files}", mod_ids=(mod_id,)))

    @staticmethod
    def _append_dependency_issues(mod: ModInfo, enabled_by_id: dict[str, list[ModInfo]], disabled_by_id: dict[str, list[ModInfo]], installed_versions: dict[str, str], issues: list[ModIssue]) -> None:
        for dependency_id, requirement in mod.dependencies.items():
            normalized_id = str(dependency_id).strip().casefold()
            if not normalized_id:
                continue
            if normalized_id not in installed_versions:
                if normalized_id in disabled_by_id:
                    message = f"{mod.name} requires '{dependency_id}', but that mod is disabled."
                    code = "dependency-disabled"
                else:
                    message = f"{mod.name} requires missing dependency '{dependency_id}' ({ModCompatibilityManager._format_requirement(requirement)})."
                    code = "dependency-missing"
                issues.append(ModIssue(severity="error", code=code, message=message, mod_ids=(mod.mod_id, normalized_id)))
                continue
            matches = ModCompatibilityManager._matches_requirement(installed_versions[normalized_id], requirement)
            if matches is False:
                issues.append(ModIssue(severity="error", code="dependency-version", message=f"{mod.name} requires '{dependency_id}' {ModCompatibilityManager._format_requirement(requirement)}, but {installed_versions[normalized_id]} is installed.", mod_ids=(mod.mod_id, normalized_id)))

        for dependency_id, requirement in mod.recommends.items():
            normalized_id = str(dependency_id).strip().casefold()
            if normalized_id and normalized_id not in installed_versions and normalized_id not in disabled_by_id:
                issues.append(ModIssue(severity="warning", code="recommended-missing", message=f"{mod.name} recommends '{dependency_id}' ({ModCompatibilityManager._format_requirement(requirement)}).", mod_ids=(mod.mod_id, normalized_id)))

    @staticmethod
    def _append_conflict_issues(mod: ModInfo, enabled_by_id: dict[str, list[ModInfo]], installed_versions: dict[str, str], issues: list[ModIssue]) -> None:
        for severity, code, declarations in (("warning", "conflict", mod.conflicts), ("error", "breaks", mod.breaks)):
            for dependency_id, requirement in declarations.items():
                normalized_id = str(dependency_id).strip().casefold()
                if normalized_id not in installed_versions:
                    continue
                matches = ModCompatibilityManager._matches_requirement(installed_versions.get(normalized_id, ""), requirement)
                if matches is not False:
                    verb = "breaks with" if code == "breaks" else "conflicts with"
                    issues.append(ModIssue(severity=severity, code=code, message=f"{mod.name} {verb} '{dependency_id}' ({ModCompatibilityManager._format_requirement(requirement)}).", mod_ids=(mod.mod_id, normalized_id)))

    @staticmethod
    def _matches_requirement(version: str, requirement: object) -> bool | None:
        if isinstance(requirement, list):
            results = [ModCompatibilityManager._matches_requirement(version, item) for item in requirement]
            if True in results:
                return True
            if results and all(result is False for result in results):
                return False
            return None
        if not isinstance(requirement, str):
            return None

        expression = requirement.strip()
        if not expression or expression == "*":
            return True
        if expression.startswith(("[", "(")) and expression.endswith(("]", ")")):
            return ModCompatibilityManager._match_maven_range(version, expression)
        if "||" in expression:
            return ModCompatibilityManager._matches_requirement(version, [part.strip() for part in expression.split("||")])

        tokens = re.findall(r"(?:>=|<=|>|<|=|\^|~)?\s*[^\s,]+", expression.replace(",", " "))
        if not tokens:
            return None
        results = [ModCompatibilityManager._match_token(version, token.replace(" ", "")) for token in tokens]
        if any(result is False for result in results):
            return False
        if all(result is True for result in results):
            return True
        return None

    @staticmethod
    def _match_maven_range(version: str, expression: str) -> bool | None:
        body = expression[1:-1].strip()
        if "," not in body:
            expected = body.strip()
            return ModCompatibilityManager._match_token(version, f"={expected}") if expected else None

        lower_text, upper_text = (part.strip() for part in body.split(",", 1))
        current = ModCompatibilityManager._version_key(version)
        if current is None:
            return None

        if lower_text:
            lower = ModCompatibilityManager._version_key(lower_text)
            if lower is None:
                return None
            if expression.startswith("["):
                if current < lower:
                    return False
            elif current <= lower:
                return False

        if upper_text:
            upper = ModCompatibilityManager._version_key(upper_text)
            if upper is None:
                return None
            if expression.endswith("]"):
                if current > upper:
                    return False
            elif current >= upper:
                return False
        return True

    @staticmethod
    def _match_token(version: str, token: str) -> bool | None:
        if token in {"", "*"}:
            return True
        match = re.fullmatch(r"(>=|<=|>|<|=|\^|~)?(.+)", token)
        if match is None:
            return None
        operator = match.group(1) or "="
        expected = match.group(2).strip()

        if any(marker in expected.casefold() for marker in ("x", "*")):
            prefix = re.split(r"[xX*]", expected, maxsplit=1)[0].rstrip(".")
            return version == prefix or version.startswith(prefix + ".")

        current_key = ModCompatibilityManager._version_key(version)
        expected_key = ModCompatibilityManager._version_key(expected)
        if current_key is None or expected_key is None:
            return version.casefold() == expected.casefold() if operator == "=" else None

        if operator == "=":
            return current_key == expected_key
        if operator == ">=":
            return current_key >= expected_key
        if operator == "<=":
            return current_key <= expected_key
        if operator == ">":
            return current_key > expected_key
        if operator == "<":
            return current_key < expected_key
        if operator == "^":
            upper = ModCompatibilityManager._caret_upper(expected_key)
            return current_key >= expected_key and current_key < upper
        if operator == "~":
            upper = (expected_key[0], expected_key[1] + 1, 0, 1, "")
            return current_key >= expected_key and current_key < upper
        return None

    @staticmethod
    def _version_key(value: str) -> tuple[int, int, int, int, str] | None:
        normalized = str(value).strip().lstrip("vV")
        without_build = normalized.split("+", 1)[0]
        numeric, separator, prerelease = without_build.partition("-")
        parts = numeric.split(".")
        if not 1 <= len(parts) <= 4 or any(not part.isdigit() for part in parts):
            return None
        numbers = [int(part) for part in parts[:3]]
        while len(numbers) < 3:
            numbers.append(0)
        release_rank = 0 if separator else 1
        extra = ".".join(parts[3:])
        suffix = prerelease.casefold() if separator else extra
        return numbers[0], numbers[1], numbers[2], release_rank, suffix

    @staticmethod
    def _caret_upper(key: tuple[int, int, int, int, str]) -> tuple[int, int, int, int, str]:
        major, minor, patch, _, _ = key
        if major > 0:
            return major + 1, 0, 0, 1, ""
        if minor > 0:
            return 0, minor + 1, 0, 1, ""
        return 0, 0, patch + 1, 1, ""

    @staticmethod
    def _format_requirement(requirement: object) -> str:
        if isinstance(requirement, list):
            return " or ".join(str(item) for item in requirement)
        return str(requirement)
