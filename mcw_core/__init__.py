"""Stable public API for the headless MCW Core library."""

from src.config import VERSION_ID as __version__
from src.models.account.account import Account
from src.models.auth.authentication import Authentication
from src.models.instance.instance import Instance
from src.models.instance.instance_state import InstanceState, InstanceStatus
from src.models.instance.instance_health import InstanceHealthIssue, InstanceHealthReport, InstanceHealthSeverity, InstanceHealthState
from src.models.runtime.process_session import ProcessSession, ProcessSessionState
from src.models.progress.progress_event import ProgressEvent
from src.models.progress.progress_stage import ProgressStage
from src.models.progress.progress_state import ProgressState
from src.models.progress.progress_unit import ProgressUnit
from src.core.instance.errors import InstanceDeletionError
from src.core.modloader.forge.compatibility_confirmation import CompatibilityConfirmationRequired
from src.core.network.download_pause import DownloadCancelledError, DownloadInterruptedError, is_download_cancelled, is_download_paused

from mcw_core.facade import MCWCore, configure_default_core, get_default_core
from mcw_core.models import InstanceCreateRequest, LaunchRequest, LaunchResult
from mcw_core.operations import OperationHandle, OperationState
from mcw_core.paths import CorePaths
from mcw_core.services import InstanceService, JavaService, LoaderService, OptiFineService

__all__ = [
    "Account",
    "Authentication",
    "CorePaths",
    "CompatibilityConfirmationRequired",
    "DownloadCancelledError",
    "DownloadInterruptedError",
    "Instance",
    "InstanceState",
    "InstanceStatus",
    "InstanceHealthIssue",
    "InstanceHealthReport",
    "InstanceHealthSeverity",
    "InstanceHealthState",
    "InstanceCreateRequest",
    "InstanceDeletionError",
    "InstanceService",
    "JavaService",
    "LaunchRequest",
    "LaunchResult",
    "LoaderService",
    "MCWCore",
    "OptiFineService",
    "OperationHandle",
    "OperationState",
    "ProgressEvent",
    "ProgressStage",
    "ProgressState",
    "ProgressUnit",
    "ProcessSession",
    "ProcessSessionState",
    "configure_default_core",
    "get_default_core",
    "is_download_cancelled",
    "is_download_paused",
]
