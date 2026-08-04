from dataclasses import dataclass


@dataclass(slots=True)
class XboxUserToken:
    token: str
    user_hash: str
    issued_at: str
    expires_at: str

    @staticmethod
    def from_dict(data: dict) -> "XboxUserToken":
        token = data.get("Token")
        issued_at = data.get("IssueInstant")
        expires_at = data.get("NotAfter")

        display_claims = data.get("DisplayClaims", {})
        xui = display_claims.get("xui", [])

        if not isinstance(token, str) or not token:
            raise ValueError("Xbox user token is missing.")

        if not isinstance(xui, list) or not xui:
            raise ValueError("Xbox user claims are missing.")

        user_hash = xui[0].get("uhs")

        if not isinstance(user_hash, str) or not user_hash:
            raise ValueError("Xbox user hash is missing.")

        return XboxUserToken(
            token=token,
            user_hash=user_hash,
            issued_at=issued_at or "",
            expires_at=expires_at or ""
        )