from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DeviceCodeResponse:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    message: str

    @staticmethod
    def from_dict(data: dict) -> DeviceCodeResponse:
        device_code = data.get("device_code")
        user_code = data.get("user_code")
        verification_uri = data.get("verification_uri") or "https://www.microsoft.com/link"
        expires_in = int(data.get("expires_in", 900))
        interval = int(data.get("interval", 5))
        message = data.get("message", "")

        if not isinstance(device_code, str) or not device_code:
            raise ValueError("Device code is missing.")
        if not isinstance(user_code, str) or not user_code:
            raise ValueError("User code is missing.")

        return DeviceCodeResponse(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_in=expires_in,
            interval=interval,
            message=message,
        )
