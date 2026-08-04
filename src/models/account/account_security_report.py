from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AccountSecurityReport:
    database_ok: bool
    account_count: int
    microsoft_account_count: int
    protected_account_count: int
    legacy_account_count: int
    invalid_account_count: int
    migrated_account_count: int = 0

    @property
    def is_healthy(self) -> bool:
        return self.database_ok and self.invalid_account_count == 0 and self.legacy_account_count == 0
