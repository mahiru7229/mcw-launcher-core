from __future__ import annotations

from pathlib import Path
from threading import RLock

from src.core.auth.account_authentication import AccountAuthentication
from src.core.auth.offline_auth import OfflineAuthentication
from src.core.instance.instance_manager import InstanceManager
from src.core.minecraft.minecraft_executor import MinecraftExecutor
from src.models.account.account import Account
from src.models.account.account_source import AccountSource
from src.models.auth.authentication import Authentication
from src.models.instance.instance import Instance

from mcw_core.models import LaunchRequest, LaunchResult
from mcw_core.operations import OperationHandle
from mcw_core.paths import CorePaths
from mcw_core.services import InstanceService, JavaService, LoaderService, OptiFineService


class MCWCore:
    """Public, GUI-independent facade for MCW Launcher core operations."""

    def __init__(self, paths: CorePaths | None = None) -> None:
        self.paths = paths or CorePaths.current()
        self.paths.apply()
        self.operations = OperationHandle()
        self.loaders = LoaderService()
        self.instances = InstanceService(self.loaders)
        self.java = JavaService()
        self.optifine = OptiFineService()

    @classmethod
    def create_default(cls, root: Path | str | None = None) -> "MCWCore":
        return cls(CorePaths.from_root(root) if root is not None else CorePaths.current())

    def launch(self, request: LaunchRequest) -> LaunchResult:
        owns_operation = not self.operations.state.active
        if owns_operation:
            self.operations.begin()
        try:
            instance = request.instance if isinstance(request.instance, Instance) else InstanceManager.load(str(request.instance))
            account, authentication = self._resolve_identity(request)
            result = MinecraftExecutor.run(
                instance=instance,
                authentication=authentication,
                account=account,
                debug_mode=request.debug_mode,
                on_progress=request.on_progress,
                on_exit=request.on_exit,
                allow_compatibility_issues_once=request.allow_compatibility_issues_once,
            )
            return LaunchResult.from_legacy(result)
        finally:
            if owns_operation:
                self.operations.finish()

    @staticmethod
    def _resolve_identity(request: LaunchRequest) -> tuple[Account, Authentication]:
        if request.account is not None:
            authentication = request.authentication or AccountAuthentication.authenticate(request.account)
            return request.account, authentication

        username = str(request.offline_username or "").strip()
        if not username:
            raise ValueError("Provide an account or an offline username.")
        account = Account(
            account_id=f"offline:{username.casefold()}",
            account_type=AccountSource.OFFLINE,
            username=username,
            uuid=OfflineAuthentication.uuid_generator(username).replace("-", ""),
        )
        return account, OfflineAuthentication.authenticate(account)


_default_core: MCWCore | None = None
_default_lock = RLock()


def get_default_core() -> MCWCore:
    global _default_core
    with _default_lock:
        if _default_core is None:
            _default_core = MCWCore.create_default()
        return _default_core


def configure_default_core(paths: CorePaths | Path | str) -> MCWCore:
    global _default_core
    normalized = paths if isinstance(paths, CorePaths) else CorePaths.from_root(paths)
    with _default_lock:
        _default_core = MCWCore(normalized)
        return _default_core
