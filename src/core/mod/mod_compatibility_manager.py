from __future__ import annotations

from collections import defaultdict
import re

from src.core.mod.mod_capability_index import ModCapabilityIndex
from src.core.mod.mod_manager import ModManager
from src.core.modloader.mod_loader_manager import ModLoaderManager
from src.models.instance.instance import Instance
from src.models.mod.mod_info import ModInfo
from src.models.mod.mod_issue import ModHealthReport, ModIssue


class ModCompatibilityManager:
    SYSTEM_DEPENDENCY_IDS = {"minecraft", "java", "forge", "neoforge", "javafml", "fml", "fabric", "fabricloader", "quilt", "quilt_loader", "quiltloader"}

    @staticmethod
    def scan(instance: Instance, mods: list[ModInfo] | None = None) -> ModHealthReport:
        mods = list(mods) if mods is not None else ModManager.list_mods(instance)
        enabled = [mod for mod in mods if mod.enabled]
        disabled = [mod for mod in mods if not mod.enabled]
        enabled_by_id: dict[str, list[ModInfo]] = defaultdict(list)
        primary_enabled_by_id: dict[str, list[ModInfo]] = defaultdict(list)
        disabled_by_id: dict[str, list[ModInfo]] = defaultdict(list)

        for mod in enabled:
            primary_id = mod.mod_id.casefold()
            if primary_id:
                primary_enabled_by_id[primary_id].append(mod)
            identities = {mod.mod_id.casefold()} | {mod_id.casefold() for mod_id, _version in mod.provided_mods if mod_id}
            for mod_id in identities:
                enabled_by_id[mod_id].append(mod)
        for mod in disabled:
            identities = {mod.mod_id.casefold()} | {mod_id.casefold() for mod_id, _version in mod.provided_mods if mod_id}
            for mod_id in identities:
                disabled_by_id[mod_id].append(mod)

        loader_name, loader_version = ModLoaderManager.normalize(instance.mod_loader)
        installed_versions: dict[str, str] = {}
        for mod in enabled:
            if mod.mod_id and mod.mod_id != "unknown":
                installed_versions.setdefault(mod.mod_id.casefold(), mod.version)
            for mod_id, version in mod.provided_mods:
                if mod_id:
                    installed_versions.setdefault(mod_id.casefold(), version or mod.version)
        installed_versions["minecraft"] = instance.version_id
        # Java is a launcher-managed environment capability. Its concrete
        # runtime is selected and validated later by JavaResolver, so dependency
        # scanning must treat it as present without trying to resolve it as a mod.
        installed_versions["java"] = "managed-runtime"
        if loader_name == ModLoaderManager.FABRIC:
            installed_versions["fabric"] = loader_version
            installed_versions["fabricloader"] = loader_version
        elif loader_name == ModLoaderManager.QUILT:
            installed_versions["quilt"] = loader_version
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

        missing_dependency_ids = {
            str(dependency_id).strip().casefold()
            for mod in enabled
            if ModCompatibilityManager._dependency_metadata_in_scope(mod, loader_name)
            for dependency_id in mod.dependencies
            if str(dependency_id).strip() and str(dependency_id).strip().casefold() not in installed_versions
        }
        if missing_dependency_ids:
            embedded_versions = ModCapabilityIndex.installed_versions(instance, enabled)
            for mod_id in missing_dependency_ids:
                version = embedded_versions.get(mod_id)
                if version:
                    installed_versions[mod_id] = version

        issues: list[ModIssue] = []
        ModCompatibilityManager._append_file_issues(mods, issues)
        ModCompatibilityManager._append_loader_issues(loader_name, enabled, issues)
        ModCompatibilityManager._append_duplicate_issues(primary_enabled_by_id, issues)

        for mod in enabled:
            if ModCompatibilityManager._dependency_metadata_in_scope(mod, loader_name):
                ModCompatibilityManager._append_dependency_issues(mod, enabled_by_id, disabled_by_id, installed_versions, issues, managed_by_modpack=mod.managed_by_modpack)
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
            if mod.managed_by_modpack:
                issues.append(
                    ModIssue(
                        severity="info",
                        code="pack-pinned-loader-metadata",
                        message=(
                            f"{mod.name} is pinned by the modpack, but its JAR metadata declares {mod.loader.title()} "
                            f"while this instance uses {loader_name.title()}. Foreign-loader dependency metadata was ignored."
                        ),
                        mod_ids=(mod.mod_id,),
                    )
                )
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
    def _dependency_metadata_in_scope(mod: ModInfo, loader_name: str) -> bool:
        if mod.loader in {"unknown", "universal", loader_name}:
            return True
        return not mod.managed_by_modpack

    @staticmethod
    def _append_duplicate_issues(enabled_by_id: dict[str, list[ModInfo]], issues: list[ModIssue]) -> None:
        for mod_id, entries in enabled_by_id.items():
            if mod_id == "unknown" or len(entries) < 2:
                continue
            files = ", ".join(item.file_name for item in entries)
            issues.append(ModIssue(severity="error", code="duplicate-mod-id", message=f"Duplicate enabled mod ID '{mod_id}': {files}", mod_ids=(mod_id,)))

    @staticmethod
    def _append_dependency_issues(mod: ModInfo, enabled_by_id: dict[str, list[ModInfo]], disabled_by_id: dict[str, list[ModInfo]], installed_versions: dict[str, str], issues: list[ModIssue], managed_by_modpack: bool = False) -> None:
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
            if normalized_id == "java" and installed_versions[normalized_id] == "managed-runtime":
                continue
            matches = ModCompatibilityManager._matches_requirement(installed_versions[normalized_id], requirement)
            if matches is False:
                if managed_by_modpack and normalized_id in ModCompatibilityManager.SYSTEM_DEPENDENCY_IDS:
                    issues.append(ModIssue(
                        severity="warning",
                        code="pack-pinned-system-requirement",
                        message=(
                            f"{mod.name} requires '{dependency_id}' {ModCompatibilityManager._format_requirement(requirement)}, "
                            f"but {installed_versions[normalized_id]} is installed. The modpack-pinned file was kept."
                        ),
                        mod_ids=(mod.mod_id, normalized_id),
                    ))
                elif managed_by_modpack and ModCompatibilityManager._is_pack_managed_dependency(enabled_by_id, normalized_id):
                    issues.append(ModIssue(
                        severity="warning",
                        code="pack-pinned-dependency-requirement",
                        message=(
                            f"{mod.name} declares '{dependency_id}' {ModCompatibilityManager._format_requirement(requirement)}, "
                            f"but the modpack pins {installed_versions[normalized_id]}. The modpack selection was accepted."
                        ),
                        mod_ids=(mod.mod_id, normalized_id),
                    ))
                else:
                    issues.append(ModIssue(severity="error", code="dependency-version", message=f"{mod.name} requires '{dependency_id}' {ModCompatibilityManager._format_requirement(requirement)}, but {installed_versions[normalized_id]} is installed.", mod_ids=(mod.mod_id, normalized_id)))

        for dependency_id, requirement in mod.recommends.items():
            normalized_id = str(dependency_id).strip().casefold()
            if normalized_id and normalized_id not in installed_versions and normalized_id not in disabled_by_id:
                issues.append(ModIssue(severity="info", code="recommended-missing", message=f"{mod.name} recommends '{dependency_id}' ({ModCompatibilityManager._format_requirement(requirement)}).", mod_ids=(mod.mod_id, normalized_id)))

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
    def _is_pack_managed_dependency(enabled_by_id: dict[str, list[ModInfo]], dependency_id: str) -> bool:
        return any(mod.managed_by_modpack for mod in enabled_by_id.get(dependency_id, ()))

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
        if "," in expression:
            alternatives = [part.strip() for part in expression.split(",") if part.strip()]
            if len(alternatives) > 1 and all(re.match(r"^(?:>=|<=|>|<|=|\^|~)", part) is None for part in alternatives):
                return ModCompatibilityManager._matches_requirement(version, alternatives)

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
            upper = (expected_key[0], expected_key[1] + 1, 0, 0, 1, ())
            return current_key >= expected_key and current_key < upper
        return None

    @staticmethod
    def _version_key(value: str) -> tuple[int, int, int, int, int, tuple[tuple[int, int, str], ...]] | None:
        normalized = str(value).strip().lstrip("vV")
        without_build = normalized.split("+", 1)[0]
        numeric, separator, prerelease = without_build.partition("-")
        parts = numeric.split(".")
        if not 1 <= len(parts) <= 4:
            return None

        core_parts = parts[:3]
        if any(not part.isdigit() for part in core_parts):
            return None

        numbers = [int(part) for part in core_parts]
        while len(numbers) < 3:
            numbers.append(0)

        extra = ".".join(parts[3:])
        revision = int(extra) if extra.isdigit() else 0
        suffix = prerelease.casefold() if separator else (extra.casefold() if extra and not extra.isdigit() else "")
        release_rank, suffix_key = ModCompatibilityManager._suffix_key(suffix)
        return numbers[0], numbers[1], numbers[2], revision, release_rank, suffix_key

    @staticmethod
    def _suffix_key(value: str) -> tuple[int, tuple[tuple[int, int, str], ...]]:
        suffix = str(value or "").strip().casefold()
        if not suffix:
            return 1, ()

        tokens = re.findall(r"\d+|[a-z]+", suffix)
        first_text = next((token for token in tokens if not token.isdigit()), "")
        prerelease = {"alpha": -5, "a": -5, "beta": -4, "b": -4, "milestone": -3, "m": -3, "rc": -2, "cr": -2, "snapshot": -1, "pre": -1, "preview": -1}
        release_aliases = {"final", "ga", "release"}
        if first_text in release_aliases and all(token in release_aliases for token in tokens if not token.isdigit()):
            return 1, ()
        release_rank = 0 if first_text in prerelease else 2
        qualifier_order = {**prerelease, "final": 0, "ga": 0, "release": 0, "sp": 1}
        key: list[tuple[int, int, str]] = []
        for token in tokens:
            if token.isdigit():
                key.append((1, int(token), ""))
            else:
                key.append((0, qualifier_order.get(token, 2), token))
        return release_rank, tuple(key)

    @staticmethod
    def _caret_upper(key: tuple[int, int, int, int, int, tuple[tuple[int, int, str], ...]]) -> tuple[int, int, int, int, int, tuple[tuple[int, int, str], ...]]:
        major, minor, patch, _, _, _ = key
        if major > 0:
            return major + 1, 0, 0, 0, 1, ()
        if minor > 0:
            return 0, minor + 1, 0, 0, 1, ()
        return 0, 0, patch + 1, 0, 1, ()

    @staticmethod
    def _format_requirement(requirement: object) -> str:
        if isinstance(requirement, list):
            return " or ".join(str(item) for item in requirement)
        return str(requirement)
