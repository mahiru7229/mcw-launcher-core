import hashlib
import uuid

from src.models.account.account import Account
from src.models.auth.authentication import Authentication


class OfflineAuthentication:
    ACCESS_TOKEN = "0"
    USER_TYPE = "legacy"

    @staticmethod
    def authenticate(account: Account) -> Authentication:
        player_name = str(account.username or "").strip()
        if not player_name:
            raise ValueError("Offline account username cannot be empty.")

        # Always rebuild the launch UUID from the player name. This avoids
        # carrying malformed, stale, Microsoft-style, or dashed UUID values
        # from older account database entries into the Minecraft command.
        launch_uuid = OfflineAuthentication.uuid_generator(player_name).replace("-", "")

        return Authentication(
            player_name=player_name,
            uuid=launch_uuid,
            access_token=OfflineAuthentication.ACCESS_TOKEN,
            xuid="",
            client_id="",
            user_type=OfflineAuthentication.USER_TYPE,
        )

    @staticmethod
    def uuid_generator(player_name: str) -> str:
        data = f"OfflinePlayer:{player_name}".encode("utf-8")
        md5 = bytearray(hashlib.md5(data, usedforsecurity=False).digest())

        # UUID version 3
        md5[6] &= 0x0F
        md5[6] |= 0x30

        # IETF variant
        md5[8] &= 0x3F
        md5[8] |= 0x80

        return str(uuid.UUID(bytes=bytes(md5)))
