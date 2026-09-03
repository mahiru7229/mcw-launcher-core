from __future__ import annotations

from typing import Any


class ManagedContentPolicy:
    INHERIT = "inherit"
    BLOCK = "block"
    ALLOW = "allow"
    ASK = "ask"
    PROVIDERS = {"modrinth", "curseforge", "forge_preflight"}

    @classmethod
    def normalize_instance(cls, value: object, default: str = INHERIT) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {cls.INHERIT, cls.BLOCK, cls.ALLOW, cls.ASK}:
            return normalized
        return default

    @classmethod
    def normalize_global(cls, value: object, default: str = BLOCK) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {cls.BLOCK, cls.ALLOW, cls.ASK}:
            return normalized
        return default

    @classmethod
    def from_legacy_bool(cls, value: object, default: bool = True) -> str:
        return cls.BLOCK if cls._as_bool(value, default) else cls.ALLOW

    @classmethod
    def resolve(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> str:
        normalized_provider = str(provider or "").strip().lower()
        if normalized_provider not in cls.PROVIDERS:
            raise ValueError(f"Unsupported managed-content provider: {provider}")

        policy_attribute = f"{normalized_provider}_failure_policy"
        instance_policy_raw = getattr(instance_settings, policy_attribute, None)
        if instance_policy_raw is None:
            legacy_attribute = f"block_launch_on_{normalized_provider}_failure"
            legacy_value = getattr(instance_settings, legacy_attribute, None)
            if legacy_value is None and normalized_provider == "curseforge":
                legacy_value = getattr(instance_settings, "block_launch_on_modrinth_failure", None)
            if legacy_value is not None:
                return cls.from_legacy_bool(legacy_value)
            instance_policy = cls.INHERIT
        else:
            instance_policy = cls.normalize_instance(instance_policy_raw)

        if instance_policy != cls.INHERIT:
            return instance_policy

        managed_content = launcher_settings.get("managed_content") if isinstance(launcher_settings, dict) else {}
        if not isinstance(managed_content, dict):
            managed_content = {}
        return cls.normalize_global(managed_content.get(policy_attribute), cls.BLOCK)

    @classmethod
    def blocks_launch(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> bool:
        return cls.resolve(instance_settings, launcher_settings, provider) == cls.BLOCK

    @classmethod
    def asks_before_launch(cls, instance_settings: object, launcher_settings: dict[str, Any], provider: str) -> bool:
        return cls.resolve(instance_settings, launcher_settings, provider) == cls.ASK

    @staticmethod
    def _as_bool(value: object, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        return default
