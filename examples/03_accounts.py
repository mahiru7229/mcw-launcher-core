from pathlib import Path
from mcw_core import CorePaths
from mcw_core.api.account.account_manager import AccountManager
from mcw_core.api.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate

CorePaths.from_root(Path.cwd() / "mcw-data").apply()
accounts = AccountManager.list_accounts()
print("accounts:", [(item.account_id, item.username, item.account_type.value) for item in accounts])

if not AccountManager.is_account_exist("ExamplePlayer"):
    offline = AccountManager.create_offline_account("ExamplePlayer")
    print("created:", offline.username)

print("Microsoft:", MicrosoftAuthenticationGate.availability())
