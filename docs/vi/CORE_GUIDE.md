# Hướng dẫn đầy đủ MCW Core 1.0.1

## 1. Mục tiêu của tài liệu

Tài liệu này giải thích cách sử dụng MCW Core để xây một launcher Minecraft độc lập. Sau khi đọc xong, người phát triển có thể:

- tạo data root và khởi động core;
- hiển thị danh sách phiên bản Minecraft;
- tạo, sửa, clone, xóa và kiểm tra instance;
- quét, chọn và cài Java;
- tạo tài khoản offline, dùng tài khoản Microsoft đã được core quản lý;
- chuẩn bị Fabric, Quilt, Forge và NeoForge;
- chạy Minecraft và nhận progress theo thời gian thực;
- pause, resume và cancel thao tác tải;
- theo dõi lúc game thoát bằng `on_exit`;
- duyệt và cài mod/modpack từ Modrinth, CurseForge và FTB;
- import `.mrpack`, CurseForge ZIP, Provider Profile và Portable MCWPack;
- export instance, provider profile và portable modpack;
- quản lý mod, resource pack, shader pack và Content Library;
- backup, restore, repair và tạo diagnostic bundle;
- nối core vào GUI PySide6 mà không khóa main thread.

## 2. Cài đặt

### Cài từ wheel

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .\mcw_core-1.0.1-py3-none-any.whl
```

Kiểm tra:

```powershell
python -c "import mcw_core; print(mcw_core.__version__)"
```

### Dependency chính

- Python `>= 3.12`;
- `httpx >= 0.28, < 1`;
- `requests >= 2.32, < 3`;
- `pywin32 >= 311` trên Windows.

Core không yêu cầu PySide6. GUI của launcher là trách nhiệm của ứng dụng gọi core.

### Lưu ý đóng gói của bản 1.0.0

Public API nằm trong `mcw_core`, nhưng wheel hiện tại vẫn mang các module triển khai tương thích dưới `src`. Người dùng thư viện **không được import trực tiếp từ `src`**. Repo core rút gọn chỉ có `mcw_core` chưa đủ để chạy độc lập nếu không đi cùng implementation tương thích. Xem [Đóng gói và phát hành](PACKAGING_RELEASE.md).

## 3. Public API và mức ổn định

### Mức 1 — Facade ổn định, nên dùng trước

```python
from mcw_core import (
    CorePaths,
    MCWCore,
    LaunchRequest,
    LaunchResult,
    InstanceCreateRequest,
    ProgressEvent,
    get_default_core,
    configure_default_core,
)
```

`MCWCore` cung cấp:

- `core.instances`: quản lý instance;
- `core.loaders`: mod loader;
- `core.java`: Java;
- `core.operations`: pause/resume/cancel;
- `core.launch(request)`: chạy game.

### Mức 2 — Public API theo module

Dùng khi cần chức năng chuyên sâu:

```python
from mcw_core.api.account.account_manager import AccountManager
from mcw_core.api.modrinth.modrinth_client import ModrinthClient
from mcw_core.api.repair.repair_service import RepairService
```

Đây vẫn là public boundary. Tuy nhiên facade ở mức 1 dễ giữ tương thích hơn giữa các phiên bản.

### Không dùng

```python
# Không nên dùng trong launcher bên thứ ba
from src.core.instance.instance_manager import InstanceManager
from src.models.instance.instance import Instance
```

## 4. Data root và cấu trúc thư mục

MCW Core giữ một cấu hình đường dẫn active cho mỗi process. Một ứng dụng thường chỉ nên dùng một root.

```python
from pathlib import Path
from mcw_core import CorePaths, MCWCore

paths = CorePaths.from_root(Path.home() / "MyLauncherData")
core = MCWCore(paths)
```

Core tạo các thư mục:

```text
MyLauncherData/
├─ cache/
├─ instances/
├─ accounts/
├─ config/
├─ logs/
├─ backups/
├─ themes/
└─ runtimes/
```

Dùng singleton mặc định:

```python
from mcw_core import configure_default_core, get_default_core

configure_default_core(r"D:\Games\MyLauncher")
core = get_default_core()
```

**Quan trọng:** `CorePaths.apply()` cập nhật registry đường dẫn toàn process. Không chạy đồng thời hai launcher root khác nhau trong cùng một Python process.

## 5. Bootstrap ứng dụng

Trước khi hiển thị màn hình chính, nên chạy bootstrap trong worker thread:

```python
from mcw_core.api.bootstrap import initialize_application

def startup_progress(percent: int, message_key: str) -> None:
    print(percent, message_key)

settings = initialize_application(startup_progress)
```

Bootstrap thực hiện:

1. tạo thư mục;
2. reconcile instance/process còn dang dở;
3. load Launcher Settings;
4. cấu hình bandwidth/concurrency;
5. phục hồi download journal và `.part`;
6. khởi tạo account database;
7. migrate bảo mật tài khoản.

`initialize_application()` trả về `dict` Launcher Settings đã chuẩn hóa.

## 6. Progress model

Callback có kiểu:

```python
Callable[[ProgressEvent], None]
```

Ví dụ:

```python
from mcw_core import ProgressEvent

def on_progress(event: ProgressEvent) -> None:
    print(event.stage.value, event.message)
    if event.is_determinate:
        print(event.current, event.total, event.percentage)
    if event.bytes_per_second is not None:
        print(f"{event.bytes_per_second / 1024 / 1024:.2f} MiB/s")
```

Các field:

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `stage` | `ProgressStage` | bước hiện tại |
| `message` | `str` | thông báo hoặc translation key |
| `current` | `int | None` | tiến độ hiện tại |
| `total` | `int | None` | tổng |
| `unit` | `ProgressUnit` | `none`, `bytes`, `files`, `steps` |
| `bytes_per_second` | `float | None` | tốc độ tải |
| `state` | `ProgressState` | running/succeeded/failed/cancelled |
| `detail` | `str` | thông tin kỹ thuật phụ |

Properties:

- `remaining`;
- `fraction` từ 0 đến 1;
- `percentage` từ 0 đến 100;
- `is_determinate`;
- `is_terminal`.

Lưu ý: một số operation cũ phát stage `FINISHED` nhưng state vẫn là `RUNNING`. Hãy xem **function return** là thành công cuối cùng và exception là thất bại; không chỉ dựa vào `event.is_terminal`.

Xem hướng dẫn chi tiết tại [PROGRESS_ASYNC.md](PROGRESS_ASYNC.md).

## 7. Instance

### Liệt kê

```python
for instance in core.instances.list():
    print(instance.name, instance.version_id, instance.mod_loader)
```

`Instance` gồm:

```python
Instance(
    instance_id: str,
    name: str,
    version_id: str,
    instance_dir: Path,
    mod_loader: tuple[str, str],
    icon: str,
    last_played: str,
    last_exit_code: int | None,
    last_launch_crashed: bool,
    last_launch_state: str,
)
```

### Tạo instance

```python
from mcw_core import InstanceCreateRequest

instance = core.instances.create(
    InstanceCreateRequest(
        name="Fabric 1.21.1",
        version_id="1.21.1",
        loader_name="fabric",
        loader_version="auto",
        on_progress=on_progress,
    )
)
```

Trả về `Instance`. Loader được resolve và prepare trước khi registry instance được tạo.

Loader hợp lệ:

- `vanilla`;
- `fabric`;
- `quilt`;
- `forge`;
- `neoforge`.

`loader_version="auto"` chọn bản ổn định tương thích.

### Load, rename, clone, delete

```python
instance = core.instances.load("Fabric 1.21.1")
core.instances.rename("Fabric 1.21.1", "Main Pack")
copy = core.instances.clone("Main Pack", "Main Pack Copy", include_saves=False)
deleted = core.instances.delete("Main Pack Copy")
```

### Status và health

```python
status = core.instances.status("Main Pack")
print(status.state, status.minecraft_pid)

health = core.instances.health("Main Pack")
print(health.state, health.healthy, health.repairable)
for issue in health.issues:
    print(issue.severity, issue.code, issue.message)
```

Runtime state và persistent health là hai khái niệm khác nhau:

- status: ready/loading/running/finished/crashed;
- health: healthy/missing files/missing Java/incomplete/corrupted...

### Icon

```python
core.instances.set_icon("Main Pack", Path("pack.png"))
core.instances.reset_icon("Main Pack")
```

## 8. Instance Settings

```python
from mcw_core.api.instance.settings_manager import SettingsManager

instance = core.instances.load("Main Pack")
settings = SettingsManager.load(instance)
settings.min_memory = 2048
settings.max_memory = 8192
settings.width = 1280
settings.height = 720
settings.fullscreen = False
SettingsManager.save(instance, settings)
```

Các field chính:

- `java_path: Path`;
- `min_memory`, `max_memory` theo MB;
- `jvm_arguments`, `game_arguments`;
- `offline_multiplayer_enabled`;
- `lan_auth_mode`, `lan_connection_provider`;
- failure policies cho Modrinth, CurseForge, Forge preflight;
- width, height, fullscreen.

Dùng helper để normalize:

```python
normalized = SettingsManager.normalize_dict({
    "min_memory": 2048,
    "max_memory": 8192,
    "width": 1280,
    "height": 720,
})
SettingsManager.save_dict(instance, normalized)
```

## 9. Minecraft versions

```python
from mcw_core.api.minecraft.version_manifest_manager import VersionManifestManager

versions = VersionManifestManager.get()
for item in versions[:20]:
    print(item.id, item.type, item.release_time)

latest_release = VersionManifestManager.latest_version(False)
latest_snapshot = VersionManifestManager.latest_version(True)
```

`get()` trả `list[VersionManifest]`. Khi mạng lỗi, core dùng manifest cache nếu có; nếu không có cache thì có thể trả danh sách rỗng.

## 10. Java và RAM

### Quét Java

```python
java_list = core.java.scan(on_progress)
for java in java_list:
    print(java.display_name, java.executable, java.valid)
```

Trả `list[JavaDiagnostic]` với major, vendor, architecture, java_home, executable và source.

### Cài Java được quản lý

```python
latest = core.java.latest_feature_release()
javaw = core.java.install(21, on_progress=on_progress, force=False)
```

`install()` trả `Path` tới `javaw.exe`.

### Memory policy

```python
from mcw_core.api.system.memory import SystemMemory, MemoryAllocationPolicy

total = SystemMemory.total_physical_memory_mb()
minimum, maximum = MemoryAllocationPolicy.normalize(1024, 8192, total)
print(total, minimum, maximum)
```

Không tự cấp toàn bộ RAM vật lý cho Minecraft. UI nên giới hạn bằng `MemoryAllocationPolicy.physical_limit_mb()` và bước 256 MB.

### dGPU

```python
from mcw_core.api.hardware.gpu_preference_manager import GpuPreferenceManager

detection = GpuPreferenceManager.detect()
if detection.has_dedicated_gpu:
    GpuPreferenceManager.apply_to_java(javaw, enabled=True)
```

Đây là best-effort Windows preference. OS/driver vẫn quyết định GPU cuối cùng.

## 11. Accounts và authentication

### Tài khoản offline

```python
from mcw_core.api.account.account_manager import AccountManager

account = AccountManager.create_offline_account("Player")
AccountManager.set_selected_account(account.account_id)
```

### Microsoft

```python
from mcw_core.api.auth.microsoft.microsoft_auth_gate import MicrosoftAuthenticationGate
from mcw_core.api.account.account_manager import AccountManager

availability = MicrosoftAuthenticationGate.availability()
if availability.enabled:
    account = AccountManager.create_microsoft_account()
```

Microsoft login là blocking và cần chạy trong worker thread. Có thể truyền `threading.Event` làm cancel event.

### Account object

`Account` chứa access/refresh token. Không log, serialize hoặc gửi object này sang analytics. Hãy để repository và security manager của core quản lý storage.

## 12. Mod loader

```python
resolved = core.loaders.resolve("1.21.1", "fabric", "auto")
print(resolved)  # ('fabric', '<resolved version>')

prepared_version, resolved = core.loaders.prepare(
    "1.21.1", "fabric", "auto", on_progress
)
```

Danh sách version loader chuyên sâu:

```python
from mcw_core.api.modloader.fabric.fabric_meta_client import FabricMetaClient
from mcw_core.api.modloader.quilt.quilt_meta_client import QuiltMetaClient
from mcw_core.api.modloader.forge.forge_metadata_client import ForgeMetadataClient
from mcw_core.api.modloader.neoforge.neoforge_metadata_client import NeoForgeMetadataClient

fabric = FabricMetaClient.list_loader_versions("1.21.1")
quilt = QuiltMetaClient.list_loader_versions("1.21.1")
forge = ForgeMetadataClient.list_versions("1.20.1")
neoforge = NeoForgeMetadataClient.list_versions("1.21.1")
```

Đổi loader instance:

```python
updated = core.instances.change_loader("Main Pack", "neoforge", "auto", on_progress)
```

Core chặn thay loader khi instance đang chạy.

## 13. Launch Minecraft

### Offline launch tối giản

```python
from mcw_core import LaunchRequest

result = core.launch(
    LaunchRequest(
        instance="Main Pack",
        offline_username="Player",
        debug_mode=False,
        on_progress=on_progress,
        on_exit=lambda exit_result: print(exit_result.to_dict()),
    )
)

print(result.java_path)
print(result.minecraft_java_major_version)
print(result.minecraft_version)
print(result.warnings)
```

### Launch với account đã lưu

```python
account = AccountManager.get_selected_account()
if account is None:
    raise RuntimeError("No account selected")

result = core.launch(
    LaunchRequest(
        instance="Main Pack",
        account=account,
        on_progress=on_progress,
        on_exit=on_game_exit,
    )
)
```

Nếu `authentication=None`, core tự dispatch Offline/Microsoft authentication dựa trên account.

### LaunchResult trả gì?

`LaunchResult` vừa là dataclass vừa implement `Mapping`:

```python
result.java_path
result.minecraft_java_major_version
result.minecraft_version
result.warnings

result["javaPath"]
result["minecraftJavaMajorVersion"]
result["minecraftVersion"]
result.as_dict()
```

**Ý nghĩa quan trọng:** `core.launch()` trả về sau khi process Minecraft đã được tạo và watcher đã được đăng ký. Nó không chờ người chơi đóng game. Khi game đóng, callback `on_exit(GameExitResult)` được gọi.

### GameExitResult

```python
def on_game_exit(result):
    print(result.exit_code)
    print(result.crashed)
    print(result.duration_seconds)
    print(result.log_path)
    print(result.crash_report_path)
```

## 14. Pause, Resume và Cancel

Để UI có thể điều khiển operation, dùng lifecycle rõ ràng:

```python
core.operations.begin()
try:
    result = core.launch(request)
finally:
    core.operations.finish()
```

Từ UI thread:

```python
core.operations.pause()
core.operations.resume()
core.operations.cancel()
```

`pause()` là cooperative: các downloader/checkpoint sẽ chờ. Nó không đóng băng JVM đã chạy. `cancel()` chủ yếu hủy giai đoạn prepare/download. Khi game đã chạy, dùng:

```python
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor
instance = core.instances.load("Main Pack")
ProcessSupervisor.stop_instance(instance)
```

Bắt cancel:

```python
from mcw_core import DownloadCancelledError, is_download_cancelled

try:
    core.launch(request)
except Exception as error:
    if is_download_cancelled(error):
        print("Cancelled")
    else:
        raise
```

## 15. Mods

```python
from pathlib import Path
from mcw_core.api.mod.mod_manager import ModManager
from mcw_core.api.mod.mod_compatibility_manager import ModCompatibilityManager

instance = core.instances.load("Main Pack")
mods = ModManager.list_mods(instance)
for mod in mods:
    print(mod.name, mod.version, mod.source, mod.managed_by_modpack)

added = ModManager.add_mods(instance, [Path("example.jar")])
ModManager.set_enabled(instance, [added[0].path], enabled=False)
report = ModCompatibilityManager.scan(instance)
```

`ModInfo` chứa metadata loader, environment, dependencies, license và provenance provider.

Mod do modpack quản lý có thể bị chặn sửa/xóa nếu operation không có launch lock token. UI nên hiện nguồn `Modrinth • Modpack`, `CurseForge • Modpack`, `FTB • Modpack` thay vì đoán theo tên file.

## 16. Modrinth

### Search

```python
from mcw_core.api.modrinth.modrinth_client import ModrinthClient

result = ModrinthClient.search_projects(
    project_type="mod",
    query="sodium",
    game_version="1.21.1",
    loader="fabric",
    index="downloads",
    offset=0,
    limit=25,
)

for project in result.projects:
    print(project.project_id, project.title, project.downloads)
```

### Detail và versions

```python
project = ModrinthClient.get_project(result.projects[0].project_id)
versions = ModrinthClient.list_project_versions(
    project.project_id,
    loader="fabric",
    game_version="1.21.1",
    version_types=("release", "beta"),
)
```

### Cài mod

```python
from mcw_core.api.modrinth.modrinth_mod_installer import ModrinthModInstaller
from mcw_core.api.progress.progress_reporter import ProgressReporter

install_result = ModrinthModInstaller.install(
    instance,
    version_id=versions[0].version_id,
    install_dependencies=True,
    reporter=ProgressReporter(on_progress),
)
```

Trả `ModrinthModInstallResult`: installed projects/files, warnings, manual downloads.

### Cài modpack

```python
from mcw_core.api.modrinth.modrinth_pack_installer import ModrinthPackInstaller

pack_result = ModrinthPackInstaller.install(
    project_id="...",
    version_id="...",
    instance_name="My Modpack",
    install_optional_files=True,
    reporter=ProgressReporter(on_progress),
    expected_loader="fabric",
    settings_override={"min_memory": 2048, "max_memory": 8192},
)
```

## 17. CurseForge

CurseForge client dùng gateway đã cấu hình. Kiểm tra trước:

```python
from mcw_core.api.curseforge.curseforge_client import CurseForgeClient

if not CurseForgeClient.is_available():
    raise RuntimeError("CurseForge gateway unavailable")
```

Search và chọn file:

```python
result = CurseForgeClient.search_projects(
    project_type="mod",
    query="jei",
    game_version="1.20.1",
    loader="forge",
)
project = result.projects[0]
files = CurseForgeClient.list_files(
    project.project_id,
    game_version="1.20.1",
    loader="forge",
    release_types=("release",),
)
```

Cài mod:

```python
from mcw_core.api.curseforge.curseforge_mod_installer import CurseForgeModInstaller

install_result = CurseForgeModInstaller.install(
    instance,
    project_id=project.project_id,
    file_id=files[0].file_id,
    install_dependencies=True,
    reporter=ProgressReporter(on_progress),
)
```

Một số file không có automatic download URL. Installer có thể trả `manual_downloads` hoặc raise manual-download exception. Launcher phải mở trang chính thức, để người dùng chọn file, rồi verify hash/size bằng manual installer.

## 18. FTB

```python
from mcw_core.api.ftb.ftb_client import FTBClient
from mcw_core.api.ftb.ftb_pack_installer import FTBPackInstaller

search = FTBClient.search_projects("academy")
project = search.projects[0]
versions = FTBClient.list_versions(project.project_id, ("release",))

result = FTBPackInstaller.install(
    project_id=project.project_id,
    version_id=versions[0].version_id,
    instance_name="FTB Pack",
    install_optional_files=True,
    reporter=ProgressReporter(on_progress),
)
```

FTB install tạo deferred manifest; file được materialize trong lần Launch đầu tiên.

## 19. Import modpack native và export

### Inspect trước khi import

```python
preview = core.instances.inspect_modpack_package(Path("pack.mrpack"))
print(preview.provider)
print(preview.package_format)
print(preview.minecraft_version)
print(preview.mod_loader)
print(preview.file_count)
```

`ProviderModpackPreview` hỗ trợ Modrinth `.mrpack`, CurseForge ZIP, Provider Profile và Portable MCWPack.

### Import

```python
instance = core.instances.import_modpack_package(
    Path("pack.mrpack"),
    on_progress=on_progress,
    settings_override={"min_memory": 2048, "max_memory": 8192},
    install_optional_files=True,
    instance_name="Imported Pack",
)
```

Import chỉ lưu manifest/overrides và tạo instance. Deferred content được tải khi launch.

### Export Provider Profile

```python
result = core.instances.export_modpack(
    "Imported Pack",
    Path("Imported-Pack-Profile.zip"),
    mode="provider_profile",
    on_progress=on_progress,
)
```

### Export Portable MCWPack

```python
result = core.instances.export_modpack(
    "Imported Pack",
    Path("Imported-Pack.mcwpack"),
    mode="portable",
    portable_mode="smart",  # hoặc "full"
    include_saves=False,
    on_progress=on_progress,
)
```

`ModpackExportResult` trả số referenced, embedded, manual files và có native package hay không.

## 20. Manual download flow

Các exception quan trọng:

- `ModrinthManagedFilesRequired`;
- `CurseForgeManagedFilesRequired`;
- `PortableManualDownloadRequired`;
- modpack archive manual-download exceptions.

Pattern:

```python
from mcw_core.api.package.portable_content_manager import PortableManualDownloadRequired

try:
    result = core.launch(request)
except PortableManualDownloadRequired as error:
    for requirement in error.requirements:
        print(requirement.project_name, requirement.project_url)
    # UI mở web, người dùng chọn các file tải về
    core.instances.install_portable_manual_files(
        error.instance.name,
        error.requirements,
        selected_paths,
    )
    # launch lại
```

Không bỏ qua hash. Không chấp nhận file chỉ vì tên giống.

## 21. Resource pack, shader pack và Content Library

```python
from mcw_core.api.content.content_pack_manager import ContentPackManager

packs = ContentPackManager.list_entries(instance, "resourcepack")
result = ContentPackManager.import_local(instance, "shaderpack", Path("shader.zip"))
ContentPackManager.set_enabled(instance, result.entry.entry_id, False)
```

Provider install:

```python
ContentPackManager.install_modrinth(instance, "resourcepack", version_id, ProgressReporter(on_progress))
```

Content Library:

```python
from mcw_core.api.content.installed_content_library import InstalledContentLibraryManager

library = InstalledContentLibraryManager.scan(instance)
for item in library.items:
    print(item.content_type, item.name, item.provider, item.status)
```

## 22. Instance package truyền thống

```python
preview = core.instances.inspect_package(Path("backup.mcwpack"))
imported = core.instances.import_package(
    Path("backup.mcwpack"),
    on_progress,
    settings_override={"max_memory": 4096},
)
exported_path = core.instances.export_package(
    "Main Pack", Path("Main-Pack.mcwpack"), include_saves=False, on_progress=on_progress
)
```

Instance package truyền thống khác Portable Modpack package. Hãy inspect modpack trước rồi mới fallback instance package, giống MCW Launcher.

## 23. Backup và Restore

```python
from mcw_core.api.backup.instance_backup_manager import InstanceBackupManager

backup = InstanceBackupManager.create(instance, scope="full", reason="before-update")
for info in InstanceBackupManager.list_backups(instance):
    print(info.path, info.created_at, info.total_size)
restore = InstanceBackupManager.restore(instance, backup.backup.path)
```

Restore có thể tạo safety backup trước khi thay file.

## 24. Repair

```python
from mcw_core.api.repair.repair_service import RepairService
from src.models.repair.repair_models import RepairMode  # model compatibility import in current wheel

report = RepairService.scan(instance, mode="quick", on_progress=on_progress)
plan = RepairService.build_plan(report)
if plan.can_repair:
    result = RepairService.repair(instance, plan, on_progress=on_progress)
```

Trong launcher bên thứ ba, nên re-export Repair enums/models từ public layer của chính ứng dụng thay vì lan truyền import `src.models`. Đây là một điểm public API 1.0.0 còn có thể cải thiện.

## 25. Diagnostics

```python
from mcw_core.api.diagnostics.diagnostics_manager import DiagnosticsManager

bundle = DiagnosticsManager.write_bundle(
    Path("diagnostics.zip"),
    launcher_version="1.0.0",
    settings=launcher_settings,
    activity_log=recent_log_text,
)
```

Diagnostics manager redacts dữ liệu nhạy cảm. Dù vậy UI vẫn nên cho người dùng xem nội dung trước khi gửi.

## 26. Process supervision và startup recovery

```python
from mcw_core.api.runtime.process_supervisor import ProcessSupervisor
from mcw_core.api.runtime.startup_recovery_manager import StartupRecoveryManager

recovery = StartupRecoveryManager.reconcile()
active = ProcessSupervisor.list_active()
```

`ProcessSession` được persist để launcher restart vẫn biết game còn chạy hay session stale.

## 27. Update API

```python
from mcw_core.api.update.update_manager import UpdateManager

manager = UpdateManager()
info = manager.check_for_update(force_refresh=True)
if info:
    prepared = manager.prepare_update(info, ProgressReporter(on_progress))
```

Apply update trên Windows nên chạy helper process riêng; không overwrite executable đang chạy từ chính process launcher.

## 28. Threading cho GUI

Hầu hết API network/download/repair là blocking. Không gọi trực tiếp từ Qt main thread.

Pattern:

```text
View click
  → Controller validates input
  → Worker thread calls MCW Core
  → Progress callback emits thread-safe signal
  → Main thread updates widgets
  → Worker returns result or exception
```

Xem code đầy đủ tại [BUILD_A_LAUNCHER.md](BUILD_A_LAUNCHER.md) và `examples/14_minimal_pyside6_launcher.py`.

## 29. Error handling chuẩn

```python
try:
    result = operation()
except DownloadCancelledError:
    show_cancelled()
except PortableManualDownloadRequired as error:
    show_manual_download_dialog(error.requirements)
except ValueError as error:
    show_validation_error(str(error))
except RuntimeError as error:
    show_operation_error(str(error))
except OSError as error:
    show_filesystem_error(str(error))
except Exception as error:
    log_exception(error)
    show_generic_error(type(error).__name__, str(error))
```

Không parse text exception để quyết định logic nếu đã có structured exception/type/fields.

## 30. Checklist một launcher hoàn chỉnh

Một launcher tối thiểu nên có:

- bootstrap và data root;
- worker/task runner;
- progress model;
- account selector;
- instance library;
- version/loader selector;
- Java scan + RAM policy;
- Launch, Pause, Cancel;
- manual-download UX;
- on-exit/crash UX;
- settings persistence;
- repair/diagnostics;
- startup recovery;
- security redaction;
- update flow;
- localization.

Đọc [BUILD_A_LAUNCHER.md](BUILD_A_LAUNCHER.md) để triển khai từng lớp.
