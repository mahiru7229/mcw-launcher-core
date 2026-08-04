from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.fs.paths import Paths


@dataclass(frozen=True, slots=True)
class CorePaths:
    """Filesystem roots used by MCW Core.

    The legacy core currently uses one process-wide path registry.  Applying a
    :class:`CorePaths` instance updates that registry, which lets a headless
    consumer run MCW Core from a portable directory or a temporary test root.
    """

    root: Path
    cache: Path | None = None
    instances: Path | None = None
    accounts: Path | None = None
    config: Path | None = None
    logs: Path | None = None
    backups: Path | None = None
    themes: Path | None = None
    runtimes: Path | None = None

    @classmethod
    def from_root(cls, root: Path | str) -> "CorePaths":
        return cls(root=Path(root).expanduser().resolve(strict=False))

    @classmethod
    def current(cls) -> "CorePaths":
        return cls(
            root=Paths.root(),
            cache=Paths.CACHE_ROOT,
            instances=Paths.INSTANCES_ROOT,
            accounts=Paths.ACCOUNTS_ROOT,
            config=Paths.CONFIG_ROOT,
            logs=Paths.LOGS_ROOT,
            backups=Paths.BACKUPS_ROOT,
            themes=Paths.THEME_ROOT,
            runtimes=Paths.RUNTIMES_ROOT,
        )

    def apply(self, initialize: bool = True) -> dict[str, Path]:
        return Paths.configure(
            self.root,
            cache_root=self.cache,
            instances_root=self.instances,
            accounts_root=self.accounts,
            config_root=self.config,
            logs_root=self.logs,
            backups_root=self.backups,
            theme_root=self.themes,
            runtimes_root=self.runtimes,
            initialize=initialize,
        )
