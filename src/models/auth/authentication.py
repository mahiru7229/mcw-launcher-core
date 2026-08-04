from dataclasses import dataclass


@dataclass(slots=True)
class Authentication:
    player_name: str
    uuid: str
    access_token: str
    xuid: str
    client_id: str
    user_type: str