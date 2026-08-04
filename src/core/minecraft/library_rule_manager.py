import platform
import re


class LibraryRuleManager:

    @staticmethod
    def is_allowed(library_data: dict) -> bool:
        rules = library_data.get("rules")

        if not rules:
            return True

        allowed = False

        for rule in rules:
            if LibraryRuleManager._is_rule_matching(rule):
                allowed = rule.get("action") == "allow"

        return allowed

    @staticmethod
    def _is_rule_matching(rule: dict) -> bool:
        os_rule = rule.get("os")

        if not os_rule:
            return True

        if not LibraryRuleManager._match_os_name(os_rule):
            return False

        if not LibraryRuleManager._match_arch(os_rule):
            return False

        if not LibraryRuleManager._match_os_version(os_rule):
            return False

        return True

    @staticmethod
    def _match_os_name(os_rule: dict) -> bool:
        required_os = os_rule.get("name")

        if not required_os:
            return True

        return required_os == LibraryRuleManager._get_current_os()

    @staticmethod
    def _match_arch(os_rule: dict) -> bool:
        required_arch = os_rule.get("arch")

        if not required_arch:
            return True

        return required_arch == LibraryRuleManager._get_current_arch()

    @staticmethod
    def _match_os_version(os_rule: dict) -> bool:
        required_version = os_rule.get("version")

        if not required_version:
            return True

        return re.search(required_version, platform.version()) is not None

    @staticmethod
    def _get_current_os() -> str:
        system = platform.system().lower()

        os_map = {
            "windows": "windows",
            "linux": "linux",
            "darwin": "osx",
        }

        return os_map.get(system, system)

    @staticmethod
    def _get_current_arch() -> str:
        architecture = platform.machine().lower()

        if architecture in ("x86", "i386", "i686"):
            return "x86"

        return "x64"