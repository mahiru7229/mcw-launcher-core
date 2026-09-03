# MCW Core v1.5.0 — Hướng dẫn tích hợp đầy đủ

> Tài liệu này dành cho người viết launcher, công cụ quản lý instance hoặc ứng dụng CLI
> sử dụng MCW Core mà không phụ thuộc GUI của MCW Launcher.

## 1. Phạm vi và phiên bản

MCW Core `1.5.0` là headless runtime đi cùng MCW Launcher `v1.5.0` Stable.

Yêu cầu phân phối:

- Python `>= 3.12`.
- Package: `mcw-core==1.5.0`.
- Không phụ thuộc PySide6 trong runtime Core.
- Public imports được hỗ trợ: `mcw_core` và `mcw_core.api.*`.
- `src.core.*` và `src.models.*` là implementation detail.
- LAN Agent được bundle cùng package.
- CurseForge gateway chỉ là source tùy chọn, không bundle endpoint/token/API key.

Kiểm tra nhanh:

```python
import importlib.metadata
import mcw_core

assert importlib.metadata.version('mcw-core') == '1.5.0'
assert mcw_core.__version__ == '1.5.0'
```

## 2. Cài đặt cho development

Linux/macOS shell:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest test -q
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest test -q
```

Nếu chỉ dùng wheel:

```bash
python -m pip install mcw_core-1.5.0-py3-none-any.whl
```

## 3. Chọn data root

Cách rõ ràng nhất cho launcher headless là cấu hình root riêng:

```python
from pathlib import Path
from mcw_core import CorePaths, MCWCore

paths = CorePaths.from_root(Path.home() / 'MCWData')
core = MCWCore(paths)
```

Các thư mục logic gồm cache, instances, accounts, config, logs, backups, themes và
runtimes. `CorePaths.apply()` cập nhật path registry process-wide, vì vậy một process nên
chỉ có một cấu hình Core đang hoạt động tại một thời điểm.

### Linux XDG

Launcher bootstrap có thể dùng XDG:

```text
config -> $XDG_CONFIG_HOME/mcw-launcher
          hoặc ~/.config/mcw-launcher

data   -> $XDG_DATA_HOME/mcw-launcher
          hoặc ~/.local/share/mcw-launcher

cache  -> $XDG_CACHE_HOME/mcw-launcher
          hoặc ~/.cache/mcw-launcher

state  -> $XDG_STATE_HOME/mcw-launcher
          hoặc ~/.local/state/mcw-launcher
```

`MCW_PORTABLE=1` giữ bootstrap ở chế độ portable. Với thư viện/headless app, truyền
`CorePaths.from_root(...)` vẫn là lựa chọn dễ kiểm soát nhất.

## 4. Khởi tạo Core

```python
from mcw_core import CorePaths, MCWCore

core = MCWCore(CorePaths.from_root('./mcw-data'))
```

Các service chính:

```python
core.instances   # InstanceService
core.loaders     # LoaderService
core.java        # JavaService
core.optifine    # OptiFineService
core.operations  # OperationHandle
```

Nếu cần singleton mặc định:

```python
from mcw_core import configure_default_core, get_default_core

configure_default_core('./mcw-data')
core = get_default_core()
```

## 5. Bootstrap ứng dụng

API granular:

```python
from mcw_core.api.bootstrap import initialize_application

settings = initialize_application(
    lambda percent, key: print(percent, key)
)
```

Bootstrap dùng cho việc chuẩn bị cấu hình/runtime cần thiết trước khi GUI hoặc CLI bắt đầu
các tác vụ chính. Host application nên chạy bootstrap ngoài UI thread nếu có thể và đưa
progress trở lại UI bằng signal/event queue.

## 6. Progress event

Callback của Core nhận `ProgressEvent`:

```python
from mcw_core import ProgressEvent

def on_progress(event: ProgressEvent) -> None:
    line = f'[{event.stage.value}] {event.message}'
    if event.is_determinate:
        line += f' {event.percentage:.1f}%'
    print(line)
```

Các model public liên quan:

- `ProgressEvent`
- `ProgressStage`
- `ProgressState`
- `ProgressUnit`

Không nên giả định mọi task đều determinate. UI cần hỗ trợ cả progress có phần trăm và
indeterminate.

## 7. Pause, resume và cancel

`OperationHandle` cung cấp cooperative control:

```python
core.operations.begin()
try:
    # long-running Core operation
    ...
finally:
    core.operations.finish()
```

Từ thread/UI khác:

```python
core.operations.pause()
core.operations.resume()
core.operations.cancel()
```

Trạng thái:

```python
state = core.operations.state
print(state.active, state.paused, state.cancel_requested)
```

Cancel không kill thread trực tiếp. Nó đặt cờ và Core ném exception tại checkpoint phù
hợp. Dùng `is_download_cancelled(error)` để phân biệt cancel do người dùng.

## 8. Minecraft version manifest

```python
from mcw_core.api.minecraft.version_manifest_manager import VersionManifestManager

versions = VersionManifestManager.get()
latest = VersionManifestManager.latest_version()
```

Host nên cache list cho UI và chỉ refresh khi người dùng yêu cầu hoặc cache hết hạn, tránh
spam metadata endpoints.

## 9. Tạo instance

Cách khuyến nghị:

```python
from mcw_core import InstanceCreateRequest

instance = core.instances.create(
    InstanceCreateRequest(
        name='Fabric 1.21.1',
        version_id='1.21.1',
        loader_name='fabric',
        loader_version='auto',
        on_progress=on_progress,
    )
)
```

Loader hỗ trợ ở facade:

```text
vanilla
fabric
forge
neoforge
quilt
```

`loader_version='auto'` để Core chọn phiên bản phù hợp. Nếu UI cho phép chọn version cụ
thể, truyền version đó sau khi lấy metadata từ module loader tương ứng.

## 10. Đọc và quản lý instance

```python
items = core.instances.list()
instance = core.instances.load('Fabric 1.21.1')
status = core.instances.status(instance)
health = core.instances.health(instance)
```

Các operation thường dùng:

```python
core.instances.rename('Old', 'New')
core.instances.clone('New', 'New Copy', include_saves=False)
core.instances.delete('New Copy')
```

Không thực hiện loader change/repair trên instance đang chạy. `InstanceService` có guard
và sẽ báo lỗi thay vì sửa dữ liệu runtime đang active.

### Metadata thư viện instance

```python
core.instances.set_library_metadata(
    'Fabric 1.21.1',
    favorite=True,
    group='Main',
    tags=['fabric', '1.21'],
)
```

### Icon

```python
core.instances.set_icon('Fabric 1.21.1', Path('icon.png'))
core.instances.reset_icon('Fabric 1.21.1')
```

## 11. Instance status, health và run lock

Public granular modules:

```python
from mcw_core.api.instance.instance_health_manager import InstanceHealthManager
from mcw_core.api.instance.instance_run_lock import InstanceRunLock
```

Run lock giúp Core biết instance nào đang chạy và chặn các thao tác có nguy cơ phá trạng
thái. Khi launcher crash, startup recovery và journal giúp phát hiện stale operation.

Không nên tự xóa file lock bằng UI trừ khi đã xác minh process tương ứng không tồn tại.

## 12. Loader

Facade:

```python
normalized = core.loaders.normalize(('forge', 'auto'))
resolved = core.loaders.resolve('1.20.1', 'forge', 'auto')
```

Đổi loader:

```python
core.instances.change_loader(
    'My Instance',
    'neoforge',
    'auto',
    on_progress=on_progress,
)
```

Repair loader:

```python
core.instances.repair_loader('My Instance', on_progress=on_progress)
```

Forge-family có thêm cơ chế restore previous loader và export diagnostics:

```python
core.instances.restore_previous_loader('My Instance', on_progress=on_progress)
core.instances.export_loader_diagnostics('My Instance', Path('loader-diagnostics.zip'))
```

### Compatibility confirmation

Forge/NeoForge có thể yêu cầu xác nhận compatibility mà không chạy lại dependency resolve
sau khi người dùng đồng ý. Khi launch, dùng callback:

```python
def confirm(error: Exception) -> bool:
    # Hiển thị warning cho người dùng rồi trả True/False.
    return True

request = LaunchRequest(
    instance='My Instance',
    offline_username='Player',
    on_compatibility_confirmation=confirm,
)
```

## 13. Java runtime

Scan Java:

```python
for runtime in core.java.scan(on_progress=on_progress):
    print(runtime)
```

Cài managed Java:

```python
java21 = core.java.install(21, on_progress=on_progress)
```

Core v1.5.0 có policy lựa chọn/provision Java 8/16/17/21 tùy Minecraft/loader.

Xem runtime profile:

```python
profile = core.instances.runtime_profile('My Instance')
print(profile.required_java_major)
print(profile.managed_java_major)
```

Chọn Java thủ công:

```python
core.instances.set_java_runtime('My Instance', '/path/to/java')
```

Truyền `None` hoặc giá trị rỗng theo contract của facade để quay về automatic selection.
Core kiểm tra Java major trước khi lưu cấu hình không tương thích.

## 14. Memory và GPU

API granular:

```python
from mcw_core.api.system.memory import SystemMemory, MemoryAllocationPolicy
from mcw_core.api.hardware.gpu_preference_manager import GpuPreferenceManager

ram_mb = SystemMemory.total_physical_memory_mb()
print(GpuPreferenceManager.detect())
```

`FirstRunRecommendationService` cung cấp recommendation dựa trên RAM/hardware cho lần chạy
đầu tiên. Host vẫn nên cho người dùng chỉnh giá trị trong giới hạn an toàn.

## 15. Account offline

```python
from mcw_core.api.account.account_manager import AccountManager

if not AccountManager.is_account_exist('Player'):
    account = AccountManager.create_offline_account('Player')
```

Hoặc launch offline trực tiếp qua facade mà không cần lưu account:

```python
result = core.launch(
    LaunchRequest(
        instance='My Instance',
        offline_username='Player',
        on_progress=on_progress,
    )
)
```

## 16. Microsoft authentication

Kiểm tra availability:

```python
from mcw_core.api.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate

availability = MicrosoftAuthenticationGate.availability()
MicrosoftAuthenticationGate.require_enabled()
```

OAuth callback server nằm trong:

```python
mcw_core.api.auth.microsoft.oauth_callback_server
```

Account token/credential không được xem như config text bình thường. Security subsystem
chịu trách nhiệm bảo vệ credential theo platform, audit integrity và migration/reprotect.

Trên Linux, package có optional platform dependencies cho keyring/Secret Service.

## 17. Launch Minecraft

Minimal offline launch:

```python
from mcw_core import LaunchRequest

result = core.launch(
    LaunchRequest(
        instance='My Instance',
        offline_username='Player',
        on_progress=on_progress,
    )
)

print(result.minecraft_version)
print(result.java_path)
print(result.minecraft_java_major_version)
```

Nếu có account đã xác thực:

```python
request = LaunchRequest(
    instance=instance,
    account=account,
    authentication=authentication,
    on_progress=on_progress,
)
result = core.launch(request)
```

Callbacks quan trọng của `LaunchRequest`:

- `on_progress`
- `on_exit`
- `on_manual_content_required`
- `on_compatibility_confirmation`
- `allow_compatibility_issues_once`

## 18. Process supervision

Các public module nâng cao:

```python
from mcw_core.api.runtime.game_runtime_manager import GameRuntimeManager
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor
from mcw_core.api.runtime.startup_recovery_manager import StartupRecoveryManager
```

v1.5.0 hỗ trợ process supervision trên Windows và Linux; Linux dùng process-group semantics
để quản lý game tree đúng hơn. Launcher không nên chỉ lưu PID rồi giả định process đã kết
thúc; hãy dùng runtime APIs để đồng bộ trạng thái.

## 19. Mod local và provenance

Public APIs:

```python
from mcw_core.api.mod.mod_manager import ModManager
from mcw_core.api.mod.mod_compatibility_manager import ModCompatibilityManager
from mcw_core.api.mod.mod_provenance_registry import ModProvenanceRegistry
```

Provenance giúp Core biết file nào đến từ provider/version nào, rất quan trọng cho update,
repair và compatibility checking. Tránh copy file provider-managed vào `mods/` rồi bỏ qua
registry nếu bạn muốn update/repair chính xác.

## 20. Modrinth

Search:

```python
from mcw_core.api.modrinth.modrinth_client import ModrinthClient

search = ModrinthClient.search_projects(
    'mod',
    'sodium',
    '1.21.1',
    'fabric',
    'downloads',
)
```

Cài mod:

```python
from mcw_core.api.modrinth.modrinth_mod_installer import ModrinthModInstaller
from mcw_core.api.progress.progress_reporter import ProgressReporter

versions = ModrinthClient.list_project_versions(
    search.projects[0].project_id,
    'fabric',
    '1.21.1',
    ('release',),
)
result = ModrinthModInstaller.install(
    instance,
    versions[0].version_id,
    install_dependencies=True,
    reporter=ProgressReporter(on_progress),
)
```

v1.5.0 còn public APIs cho mod update, pack install, pack repair, pack update và registry.

## 21. CurseForge

Core **không bundle CurseForge API key**. Kiểm tra gateway:

```python
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient

if not CurseForgeClient.is_available():
    raise RuntimeError('CurseForge gateway is unavailable')
```

Search và install:

```python
search = CurseForgeClient.search_projects(
    'mod', 'jei', instance.version_id, 'forge'
)
project = search.projects[0]
files = CurseForgeClient.list_files(
    project.project_id,
    instance.version_id,
    'forge',
    ('release',),
)
```

Gateway source nằm trong `mcw-curseforge-gateway-main.zip`. Deployment phải tự cung cấp
`CURSEFORGE_API_KEY` và cấu hình HTTPS endpoint cho Core. Không hard-code API key vào desktop
client.

`curseforge_links` là public module mới trong v1.5.0 để tạo/chuẩn hóa các liên kết provider.

## 22. FTB

Client public:

```python
from mcw_core.api.ftb.ftb_client import FTBClient

result = FTBClient.search_projects('search text')
project = FTBClient.get_project(result.projects[0].project_id)
versions = FTBClient.list_versions(project.project_id)
```

Các module public gồm client, content manager, pack installer và pack registry.

## 23. ATLauncher

ATLauncher là provider public đầy đủ trong v1.5.0:

```python
from mcw_core.api.atlauncher.atlauncher_client import ATLauncherClient

result = ATLauncherClient.search_projects('search text')
project = ATLauncherClient.get_project(result.projects[0].safe_name)
versions = ATLauncherClient.list_versions(project.safe_name)
```

Cài pack:

```python
from mcw_core.api.atlauncher.atlauncher_pack_installer import ATLauncherPackInstaller

installed = ATLauncherPackInstaller.install(
    safe_name=project.safe_name,
    version_name=versions[0].version,
    instance_name='ATLauncher Pack',
    install_optional_files=True,
)
```

Xem API Reference để kiểm tra chính xác model field của provider version bạn đang dùng;
không nên hard-code field name từ UI nếu provider model thay đổi.

## 24. Modpack import/export

Inspect package:

```python
preview = core.instances.inspect_modpack_package(Path('example.mrpack'))
```

Import:

```python
instance = core.instances.import_modpack_package(
    Path('example.mrpack'),
    on_progress=on_progress,
    settings_override={'min_memory': 2048, 'max_memory': 8192},
    instance_name='Imported Pack',
)
```

Export:

```python
output = core.instances.export_modpack(
    instance.name,
    Path('portable.mcwpack'),
    mode='portable',
    portable_mode='smart',
    include_saves=False,
    on_progress=on_progress,
)
```

Chi tiết format xem [../PACKAGE_FORMAT.md](../PACKAGE_FORMAT.md).

## 25. Portable manual content

Một số file không thể tự tải vì policy/provider. Khi launch/import, Core có thể ném
`PortableManualDownloadRequired`.

```python
from mcw_core.api.package.portable_content_manager import PortableManualDownloadRequired

try:
    core.launch(LaunchRequest(instance='Portable Pack', offline_username='Player'))
except PortableManualDownloadRequired as error:
    for requirement in error.requirements:
        print(requirement.project_name, requirement.file_name, requirement.project_url)
```

Sau khi người dùng tự tải file:

```python
core.instances.install_portable_manual_files(
    error.instance.name,
    error.requirements,
    selected_paths,
)
```

## 26. Content packs và installed content library

```python
from mcw_core.api.content.installed_content_library import InstalledContentLibraryManager
from mcw_core.api.content.content_pack_manager import ContentPackManager

library = InstalledContentLibraryManager.scan(instance)
for item in library.items:
    print(item.content_type, item.name, item.provider, item.status)
```

Content library cho phép UI hợp nhất mod/resourcepack/shader/provider content thành một view
thay vì đọc thư mục thô.

## 27. OptiFine

Facade v1.5.0:

```python
version = core.optifine.inspect_file(Path('OptiFine.jar'))
compat = core.optifine.compatibility(instance, version)
result = core.optifine.install(instance, Path('OptiFine.jar'), on_progress=on_progress)
state = core.optifine.state(instance)
```

Repair/uninstall:

```python
core.optifine.repair(instance, on_progress=on_progress)
core.optifine.uninstall(instance)
```

OptiFine là file do người dùng cung cấp; host nên hiển thị official download URL từ
`OptiFineService.OFFICIAL_DOWNLOADS_URL` thay vì tự mirror binary.

## 28. Backup

```python
from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager

backup = InstanceBackupManager.create(
    instance,
    scope='full',
    reason='manual',
)
```

Nên tạo backup trước thao tác có rủi ro cao như import/repair lớn nếu workflow không tự tạo
transaction snapshot.

## 29. Repair

Facade scan/execute:

```python
report = core.instances.scan_repair('My Instance', 'quick', on_progress=on_progress)
```

Granular API:

```python
from mcw_core.api.repair.repair_service import RepairService

report = RepairService.scan(instance, mode='quick', on_progress=on_progress)
plan = RepairService.build_plan(report)
if plan.can_repair:
    result = RepairService.repair(instance, plan, on_progress=on_progress)
```

UI nên tách `scan -> review -> repair` để người dùng biết Core định thay đổi gì.

## 30. Diagnostics và issue report

```python
from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager

DiagnosticsManager.write_bundle(
    Path('diagnostics.zip'),
    '1.5.0',
    settings={},
    activity_log='',
)
```

`IssueReportBuilder` trong v1.5.0 có thể chuẩn hóa detail, tạo GitHub issue body và URL mở
issue mới. Trước khi xuất diagnostics, dữ liệu nhạy cảm phải qua redaction layer.

## 31. Sensitive data redaction

```python
from mcw_core.api.security.sensitive_data_redactor import SensitiveDataRedactor

safe = SensitiveDataRedactor.redact_json(payload)
```

Không log access token, refresh token, password, keyring secret, CurseForge API key hoặc
các giá trị cấu hình nhạy cảm ở dạng thô.

## 32. Network session và connectivity

Connectivity snapshot:

```python
from mcw_core.api.network.connectivity_monitor import ConnectivityMonitor

snapshot = ConnectivityMonitor.probe(force=False)
```

Các module network public còn gồm:

- `network_session`
- `download_manager`
- `download_bandwidth_limiter`
- `download_pause`

UI có thể dùng connectivity snapshot để giải thích offline/cache mode, nhưng không nên coi
một probe thất bại là bằng chứng tuyệt đối rằng Internet mất hoàn toàn.

## 33. Shared content store

```python
from mcw_core.api.storage.content_store import ContentStore

result = ContentStore.adopt(Path('downloaded-file.jar'))
```

Store dùng SHA-256 để nhận diện blob. `materialize(...)` có thể tái sử dụng file và ưu tiên
hardlink khi an toàn. Mục tiêu là giảm duplicate binary giữa instance/provider downloads.

Provider API/metadata cache là lớp khác và không bị cleanup như binary store.

## 34. Legacy storage cleanup

```python
from mcw_core.api.storage.legacy_storage_migration_service import LegacyStorageMigrationService

probe = LegacyStorageMigrationService.probe()
plan = LegacyStorageMigrationService.scan()
```

Nếu người dùng xác nhận:

```python
result = LegacyStorageMigrationService.apply(plan)
```

Cleanup có retention cho unused Minecraft version JAR và revalidate reference trước khi
xóa. Không nên tự xóa các candidate bằng path từ UI; hãy gọi service để giữ các guard.

## 35. Platform storage migration

```python
from mcw_core.api.storage.platform_storage_migration import PlatformStorageMigration

report = PlatformStorageMigration.migrate()
```

Đây là workflow chuyển dữ liệu legacy sang layout platform-aware (đặc biệt Linux XDG).
Host nên hiển thị report thay vì giả định migration luôn có file để chuyển.

## 36. Update check và prepare

```python
from mcw_core.api.update.update_manager import UpdateManager

info = UpdateManager.check_for_update(force_refresh=True)
if info:
    prepared = UpdateManager.prepare_update(info)
```

Automatic installer:

```python
from mcw_core.api.update.automatic_update_installer import AutomaticUpdateInstaller

if AutomaticUpdateInstaller.is_supported():
    helper = AutomaticUpdateInstaller.launch(prepared)
```

v1.5.0 có Windows và Linux installer public. Package update cần được verify trước khi apply;
không thay updater bằng unzip trực tiếp vào install directory.

Chi tiết xem [../UPDATE_PACKAGES.md](../UPDATE_PACKAGES.md).

## 37. Language packs

Language runtime nằm ở:

```python
from mcw_core.api.language.language_manager import LanguageManager
```

Source distribution có `lang/en-US.json` và `lang/vi-VN.json`. Contract chi tiết:
[../LANGUAGE_PACKS.md](../LANGUAGE_PACKS.md).

## 38. Theme runtime

Public theme modules:

```text
mcw_core.api.theme.theme_manager
mcw_core.api.theme.theme_palette
mcw_core.api.theme.theme_font
mcw_core.api.theme.theme_motion
mcw_core.api.theme.theme_animation
mcw_core.api.theme.theme_authoring
```

Schema và authoring guide nằm trong `docs/schema/`, `docs/theme-template/` và bộ tài liệu
`THEME_*`.

Theme là presentation contract; Core vẫn headless và không phụ thuộc Qt.

## 39. LAN Agent

Public modules:

```python
from mcw_core.api.lan.lan_agent_manager import LanAgentManager
from mcw_core.api.lan.lan_hosting_manager import LanHostingManager
```

LAN Agent JAR được bundle trong package resource. Launcher nên dùng manager API để materialize
và chọn target thay vì giả định path JAR cố định trong wheel.

## 40. CLI

Package cài command:

```bash
mcw-core-launch --root ./mcw-data --list
mcw-core-launch --root ./mcw-data --instance "My Instance" --username Player
```

CLI hữu ích cho smoke test headless, CI hoặc kiểm tra data root mà không cần GUI.

## 41. Threading khi tích hợp GUI

Không chạy download/install/repair/launch preparation trực tiếp trên UI thread.

Pattern khuyến nghị:

```text
UI thread
  | create request
  v
worker thread / executor
  | Core operation
  | progress callback
  v
thread-safe signal/event queue
  |
  v
UI updates
```

Ví dụ PySide6 đầy đủ nằm ở `examples/13_minimal_pyside6_launcher.py`. PySide6 là dependency
của application example, không phải dependency runtime của Core.

## 42. Error handling

Không catch `Exception` rồi bỏ qua. Tách ít nhất:

- cancel do người dùng
- provider unavailable / offline
- manual download required
- compatibility confirmation required
- instance already running / mod change blocked
- invalid Java/runtime
- corrupted package / checksum
- authentication disabled/locked
- unexpected Core bug

Với unexpected error, tạo diagnostics bundle đã redact và cho người dùng đường dẫn report.

## 43. Cache và offline behavior

Provider clients có API cache status/clear cache ở nhiều provider. UI nên phân biệt:

- metadata cache
- downloaded binary/shared content store
- instance-local files
- update cache

Không dùng nút “Clear cache” để xóa tất cả các lớp một cách mù quáng.

## 44. Recommended launcher startup sequence

```text
1. Chọn CorePaths / platform storage
2. Chạy platform migration nếu cần
3. initialize_application(...)
4. startup recovery
5. account security audit/migration
6. load launcher settings
7. load instance list/status/health
8. probe connectivity (không blocking UI)
9. check update theo policy
10. hiển thị UI ready
```

Tùy launcher, một số bước có thể chạy song song sau khi path/bootstrap đã ổn định.

## 45. Recommended instance creation sequence

```text
user chooses MC version
        |
        v
choose loader + version/auto
        |
        v
InstanceCreateRequest
        |
        v
core.instances.create(...)
        |
        +--> resolve MC metadata
        +--> prepare loader
        +--> create instance metadata
        +--> progress events
        v
configure Java/memory/content
```

## 46. Recommended launch sequence

```text
validate instance/status
        |
        v
begin OperationHandle (optional owner)
        |
        v
MCWCore.launch(LaunchRequest)
        |
        +--> identity/auth
        +--> instance health/runtime checks
        +--> provider/manual content checks
        +--> Java selection/provisioning
        +--> game libraries/assets/natives
        +--> arguments/classpath
        +--> run lock + process supervision
        v
LaunchResult + on_exit callback
```

`MCWCore.launch()` tự quản lý operation state nếu caller chưa `begin()`. Nếu application
bao nhiều thao tác trong cùng một operation, caller có thể tự `begin()/finish()`.

## 47. Public API boundary khi viết plugin/extension

Ưu tiên:

```python
import mcw_core
from mcw_core import ...
from mcw_core.api.some_domain.some_module import ...
```

Tránh:

```python
from src.core... import ...
from src.models... import ...
```

Lý do: `src.*` có thể được refactor mà không giữ compatibility cho external consumer.

## 48. Test và release verification

Source distribution v1.5.0 ghi nhận release verification:

```text
Core source regression: 1572 passed
CurseForge gateway: 18 passed
Core release preflight: passed
Python compileall: passed
Wheel metadata/content audit: passed
Headless boundary: no src/gui or PySide6 dependency
```

Khi sửa Core, tối thiểu chạy:

```bash
python -m compileall -q mcw_core src
python -m pytest test -q
python tools/core_release_preflight.py
```

## 49. API reference

Reference được sinh từ source public v1.5.0, gồm toàn bộ module non-`__init__` dưới
`mcw_core/api/`:

- [API_REFERENCE.md](API_REFERENCE.md) — Vietnamese header + source-derived signatures.
- [../en/API_REFERENCE.md](../en/API_REFERENCE.md) — English header + source-derived signatures.

Khi thêm public module/class/method, chạy:

```bash
python tools/generate_public_api_docs.py
```

## 50. Tài liệu chuyên sâu

- Instance: [../INSTANCE_SYSTEM.md](../INSTANCE_SYSTEM.md)
- Package: [../PACKAGE_FORMAT.md](../PACKAGE_FORMAT.md)
- Modrinth: [../MODRINTH_INTEGRATION.md](../MODRINTH_INTEGRATION.md)
- Forge + Modrinth: [../FORGE_MODRINTH.md](../FORGE_MODRINTH.md)
- Forge + CurseForge: [../FORGE_CURSEFORGE.md](../FORGE_CURSEFORGE.md)
- Update: [../UPDATE_PACKAGES.md](../UPDATE_PACKAGES.md)
- Language: [../LANGUAGE_PACKS.md](../LANGUAGE_PACKS.md)
- Theme: [../THEME_CREATION_GUIDE.md](../THEME_CREATION_GUIDE.md)
- Theme runtime contract: [../THEME_RUNTIME_CONTRACT.md](../THEME_RUNTIME_CONTRACT.md)
- Migration: [../MIGRATION.md](../MIGRATION.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
