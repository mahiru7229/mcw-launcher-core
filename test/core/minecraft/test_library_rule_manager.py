import re

import pytest

from src.core.minecraft.library_rule_manager import LibraryRuleManager


def test_library_without_rules_is_allowed():
    library_data = {
        "name": "com.example:example:1.0"
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_empty_rules_are_allowed():
    library_data = {
        "rules": []
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_matching_allow_rule_is_allowed(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_is_rule_matching",
        lambda rule: True
    )

    library_data = {
        "rules": [
            {"action": "allow"}
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_matching_disallow_rule_is_rejected(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_is_rule_matching",
        lambda rule: True
    )

    library_data = {
        "rules": [
            {"action": "disallow"}
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is False


def test_non_matching_rule_does_not_change_result(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_is_rule_matching",
        lambda rule: False
    )

    library_data = {
        "rules": [
            {"action": "allow"}
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is False


def test_last_matching_rule_wins(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_is_rule_matching",
        lambda rule: True
    )

    library_data = {
        "rules": [
            {"action": "allow"},
            {"action": "disallow"},
            {"action": "allow"}
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_non_matching_rule_does_not_override_previous_match(
    monkeypatch: pytest.MonkeyPatch
):
    matching_rules = {
        "windows": True,
        "linux": False
    }

    monkeypatch.setattr(
        LibraryRuleManager,
        "_is_rule_matching",
        lambda rule: matching_rules[rule["id"]]
    )

    library_data = {
        "rules": [
            {
                "id": "windows",
                "action": "allow"
            },
            {
                "id": "linux",
                "action": "disallow"
            }
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_rule_without_os_matches_every_platform():
    rule = {
        "action": "allow"
    }

    assert LibraryRuleManager._is_rule_matching(rule) is True


def test_rule_matches_when_os_arch_and_version_match(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_os_name",
        lambda os_rule: True
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_arch",
        lambda os_rule: True
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_os_version",
        lambda os_rule: True
    )

    rule = {
        "action": "allow",
        "os": {
            "name": "windows",
            "arch": "x64",
            "version": "^10\\."
        }
    }

    assert LibraryRuleManager._is_rule_matching(rule) is True


@pytest.mark.parametrize(
    (
        "os_matches",
        "arch_matches",
        "version_matches"
    ),
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ]
)
def test_rule_is_rejected_when_any_os_condition_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
    os_matches: bool,
    arch_matches: bool,
    version_matches: bool
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_os_name",
        lambda os_rule: os_matches
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_arch",
        lambda os_rule: arch_matches
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_match_os_version",
        lambda os_rule: version_matches
    )

    rule = {
        "action": "allow",
        "os": {
            "name": "windows",
            "arch": "x64",
            "version": "^10\\."
        }
    }

    assert LibraryRuleManager._is_rule_matching(rule) is False


def test_os_name_without_requirement_matches():
    assert LibraryRuleManager._match_os_name({}) is True


def test_os_name_matches_current_os(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_os",
        lambda: "windows"
    )

    assert LibraryRuleManager._match_os_name(
        {"name": "windows"}
    ) is True


def test_os_name_rejects_different_os(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_os",
        lambda: "linux"
    )

    assert LibraryRuleManager._match_os_name(
        {"name": "windows"}
    ) is False


def test_arch_without_requirement_matches():
    assert LibraryRuleManager._match_arch({}) is True


def test_arch_matches_current_architecture(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_arch",
        lambda: "x64"
    )

    assert LibraryRuleManager._match_arch(
        {"arch": "x64"}
    ) is True


def test_arch_rejects_different_architecture(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_arch",
        lambda: "x86"
    )

    assert LibraryRuleManager._match_arch(
        {"arch": "x64"}
    ) is False


def test_os_version_without_requirement_matches():
    assert LibraryRuleManager._match_os_version({}) is True


def test_os_version_regex_matches(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.version",
        lambda: "10.0.26100"
    )

    assert LibraryRuleManager._match_os_version(
        {"version": "^10\\."}
    ) is True


def test_os_version_regex_rejects_non_matching_version(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.version",
        lambda: "6.1.0"
    )

    assert LibraryRuleManager._match_os_version(
        {"version": "^10\\."}
    ) is False


def test_invalid_os_version_regex_raises_error(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.version",
        lambda: "10.0.26100"
    )

    with pytest.raises(re.error):
        LibraryRuleManager._match_os_version(
            {"version": "["}
        )


@pytest.mark.parametrize(
    ("platform_name", "expected"),
    [
        ("Windows", "windows"),
        ("Linux", "linux"),
        ("Darwin", "osx"),
        ("FreeBSD", "freebsd"),
    ]
)
def test_get_current_os_maps_platform_name(
    monkeypatch: pytest.MonkeyPatch,
    platform_name: str,
    expected: str
):
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.system",
        lambda: platform_name
    )

    assert LibraryRuleManager._get_current_os() == expected


@pytest.mark.parametrize(
    "machine_name",
    [
        "x86",
        "i386",
        "i686",
    ]
)
def test_get_current_arch_maps_32_bit_x86(
    monkeypatch: pytest.MonkeyPatch,
    machine_name: str
):
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.machine",
        lambda: machine_name
    )

    assert LibraryRuleManager._get_current_arch() == "x86"


@pytest.mark.parametrize(
    "machine_name",
    [
        "AMD64",
        "x86_64",
        "arm64",
        "aarch64",
    ]
)
def test_get_current_arch_maps_other_architectures_to_x64(
    monkeypatch: pytest.MonkeyPatch,
    machine_name: str
):
    """
    This documents the current implementation.

    Note: arm64 and aarch64 are currently treated as x64.
    If ARM support is added later, this test should be changed.
    """
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.machine",
        lambda: machine_name
    )

    assert LibraryRuleManager._get_current_arch() == "x64"


def test_real_windows_allow_rule(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_os",
        lambda: "windows"
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_arch",
        lambda: "x64"
    )
    monkeypatch.setattr(
        "src.core.minecraft.library_rule_manager.platform.version",
        lambda: "10.0.26100"
    )

    library_data = {
        "rules": [
            {
                "action": "allow",
                "os": {
                    "name": "windows",
                    "arch": "x64",
                    "version": "^10\\."
                }
            }
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is True


def test_real_windows_disallow_rule_overrides_general_allow(
    monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_os",
        lambda: "windows"
    )
    monkeypatch.setattr(
        LibraryRuleManager,
        "_get_current_arch",
        lambda: "x64"
    )

    library_data = {
        "rules": [
            {
                "action": "allow"
            },
            {
                "action": "disallow",
                "os": {
                    "name": "windows"
                }
            }
        ]
    }

    assert LibraryRuleManager.is_allowed(library_data) is False