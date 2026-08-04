from __future__ import annotations

from dataclasses import dataclass

from src.config import MICROSOFT_AUTH_ENABLED, MICROSOFT_AUTH_STATUS


class MicrosoftAuthenticationLockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MicrosoftAuthenticationAvailability:
    enabled: bool
    status: str
    message: str


class MicrosoftAuthenticationGate:
    @staticmethod
    def availability() -> MicrosoftAuthenticationAvailability:
        enabled = bool(MICROSOFT_AUTH_ENABLED)
        status = str(MICROSOFT_AUTH_STATUS or "disabled")
        if enabled:
            status = "available"
            message = "Microsoft authentication is available."
        elif status == "pending_mojang_approval":
            message = "Microsoft account sign-in is prepared but locked while MCW Launcher waits for Mojang/Microsoft application approval."
        else:
            message = "Microsoft account sign-in is currently disabled."
        return MicrosoftAuthenticationAvailability(enabled=enabled, status=status, message=message)

    @staticmethod
    def require_enabled() -> None:
        availability = MicrosoftAuthenticationGate.availability()
        if not availability.enabled:
            raise MicrosoftAuthenticationLockedError(availability.message)
