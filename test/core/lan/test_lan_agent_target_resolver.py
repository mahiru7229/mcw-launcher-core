from pathlib import Path
from types import SimpleNamespace
import struct
import zipfile

import pytest

from src.core.fs.paths import Paths
from src.core.lan.lan_agent_target_resolver import LanAgentTarget, LanAgentTargetResolver
from src.models.instance.instance import Instance


def make_instance(tmp_path: Path, version_id: str = "1.20.1", loader: str = "fabric") -> Instance:
    return Instance(instance_id="pack", name="Pack", version_id=version_id, instance_dir=tmp_path / "Pack", mod_loader=(loader, "test"))


def make_version(mapping_path: Path | None = None, intermediary_path: Path | None = None, game_arguments: list[str] | None = None) -> SimpleNamespace:
    downloads = {}
    libraries = []
    if mapping_path is not None:
        downloads["client_mappings"] = {
            "url": "https://example.invalid/client.txt",
            "sha1": "0" * 40,
            "size": mapping_path.stat().st_size,
        }
    if intermediary_path is not None:
        libraries.append(
            {
                "name": "net.fabricmc:intermediary:1.20.1",
                "downloads": {"artifact": {"path": "net/fabricmc/intermediary/1.20.1/intermediary-1.20.1.jar"}},
            }
        )
    arguments = {"game": list(game_arguments or [])}
    return SimpleNamespace(id="fabric-loader-test-1.20.1", raw_json={"downloads": downloads, "arguments": arguments}, downloads=downloads, libraries=libraries, arguments=arguments)


def write_mojang_mappings(path: Path) -> None:
    path.write_text(
        "# synthetic Mojang mappings\n"
        "net.minecraft.server.MinecraftServer -> net.minecraft.server.MinecraftServer:\n"
        "    100:100:void setDifficultyLocked(boolean) -> b\n"
        "    101:101:void setOnlineMode(boolean) -> d\n",
        encoding="utf-8",
    )


def write_tiny_v2(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "tiny\t2\t0\tofficial\tintermediary\n"
        "c\tnet/minecraft/server/MinecraftServer\tnet/minecraft/server/MinecraftServer\n"
        "\tm\t(Z)V\td\tmethod_3864\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mappings/mappings.tiny", payload)


def write_tiny_v1(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "v1\tofficial\tintermediary\n"
        "CLASS\tnet/minecraft/server/MinecraftServer\tnet/minecraft/server/MinecraftServer\n"
        "METHOD\tnet/minecraft/server/MinecraftServer\t(Z)V\td\tmethod_3864\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mappings/mappings.tiny", payload)


def write_tiny_v1_identity_class_omitted(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "v1\tofficial\tintermediary\n"
        "METHOD\tnet/minecraft/server/MinecraftServer\t(Ljava/nio/file/Path;)V\td\tmethod_21615\n"
        "METHOD\tnet/minecraft/server/MinecraftServer\t(Z)V\td\tmethod_3864\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mappings/mappings.tiny", payload)




def write_class_jar(path: Path, methods: list[tuple[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    constant_pool: list[bytes] = []

    def utf8(value: str) -> int:
        encoded = value.encode("utf-8")
        constant_pool.append(b"\x01" + struct.pack(">H", len(encoded)) + encoded)
        return len(constant_pool)

    dummy_name_index = utf8("Dummy")
    constant_pool.append(b"\x07" + struct.pack(">H", dummy_name_index))
    dummy_class_index = len(constant_pool)
    object_name_index = utf8("java/lang/Object")
    constant_pool.append(b"\x07" + struct.pack(">H", object_name_index))
    object_class_index = len(constant_pool)

    method_indexes: list[tuple[int, int]] = []
    for name, descriptor in methods:
        method_indexes.append((utf8(name), utf8(descriptor)))

    payload = bytearray()
    payload.extend(struct.pack(">IHHH", 0xCAFEBABE, 0, 61, len(constant_pool) + 1))
    for entry in constant_pool:
        payload.extend(entry)
    payload.extend(struct.pack(">HHHH", 0x0021, dummy_class_index, object_class_index, 0))
    payload.extend(struct.pack(">H", 0))
    payload.extend(struct.pack(">H", len(method_indexes)))
    for name_index, descriptor_index in method_indexes:
        payload.extend(struct.pack(">HHHH", 0x0001, name_index, descriptor_index, 0))
    payload.extend(struct.pack(">H", 0))

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("net/minecraft/server/MinecraftServer.class", payload)


def test_parse_mojang_mappings_accepts_legacy_set_online_mode_name(tmp_path: Path) -> None:
    mapping_path = tmp_path / "client.txt"
    write_mojang_mappings(mapping_path)

    target = LanAgentTargetResolver._parse_mojang_client_mappings(mapping_path)

    assert target == LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d")


@pytest.mark.parametrize("writer", [write_tiny_v1, write_tiny_v1_identity_class_omitted, write_tiny_v2])
def test_parse_fabric_intermediary_mapping_formats(tmp_path: Path, writer) -> None:
    mapping_jar = tmp_path / "intermediary.jar"
    writer(mapping_jar)
    official = LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d")

    target = LanAgentTargetResolver._parse_intermediary_mappings(mapping_jar, official)

    assert target == LanAgentTarget("intermediary", "net/minecraft/server/MinecraftServer", "method_3864")


def test_resolve_fabric_1201_emits_intermediary_official_and_named_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping_path = tmp_path / "client.txt"
    write_mojang_mappings(mapping_path)
    intermediary_path = tmp_path / "libraries" / "net/fabricmc/intermediary/1.20.1/intermediary-1.20.1.jar"
    write_tiny_v1_identity_class_omitted(intermediary_path)
    version = make_version(mapping_path, intermediary_path)
    instance = make_instance(tmp_path)

    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    monkeypatch.setattr(
        LanAgentTargetResolver,
        "_ensure_client_mappings",
        classmethod(lambda cls, _version, _game_version, _reporter: mapping_path),
    )

    resolution = LanAgentTargetResolver.resolve(version, instance)

    assert resolution.targets[0] == LanAgentTarget("intermediary", "net/minecraft/server/MinecraftServer", "method_3864")
    assert LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d") in resolution.targets
    assert LanAgentTarget("named", "net/minecraft/server/MinecraftServer", "setOnlineMode") in resolution.targets
    assert resolution.warnings == ()


def test_resolve_forge_1201_emits_srg_official_and_named_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping_path = tmp_path / "client.txt"
    write_mojang_mappings(mapping_path)
    version = make_version(mapping_path, game_arguments=["--fml.mcpVersion", "20230612.114412"])
    instance = make_instance(tmp_path, loader="forge")
    monkeypatch.setattr(LanAgentTargetResolver, "_ensure_client_mappings", classmethod(lambda cls, _version, _game_version, _reporter: mapping_path))
    monkeypatch.setattr(
        LanAgentTargetResolver,
        "_resolve_forge_srg_target",
        classmethod(lambda cls, _version, _game_version, _official: LanAgentTarget("forge-srg", "net/minecraft/server/MinecraftServer", "m_129985_")),
    )

    resolution = LanAgentTargetResolver.resolve(version, instance)

    assert resolution.targets[0] == LanAgentTarget("forge-srg", "net/minecraft/server/MinecraftServer", "m_129985_")
    assert LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d") in resolution.targets
    assert LanAgentTarget("named", "net/minecraft/server/MinecraftServer", "setOnlineMode") in resolution.targets
    assert resolution.warnings == ()


def test_resolve_forge_srg_target_matches_method_table_ordinal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slim_jar = tmp_path / "client-slim.jar"
    srg_jar = tmp_path / "client-srg.jar"
    write_class_jar(slim_jar, [("a", "()V"), ("d", "(Z)V"), ("e", "(Z)V")])
    write_class_jar(srg_jar, [("m_1_", "()V"), ("m_129985_", "(Z)V"), ("m_129993_", "(Z)V")])
    monkeypatch.setattr(LanAgentTargetResolver, "_find_forge_runtime_jars", classmethod(lambda cls, _version, _game_version: (slim_jar, srg_jar)))

    target = LanAgentTargetResolver._resolve_forge_srg_target(make_version(), "1.20.1", LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d"))

    assert target == LanAgentTarget("forge-srg", "net/minecraft/server/MinecraftServer", "m_129985_")


def test_find_forge_runtime_jars_uses_mcp_version_from_game_arguments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "libraries" / "net/minecraft/client/1.20.1-20230612.114412"
    slim_jar = directory / "client-1.20.1-20230612.114412-slim.jar"
    srg_jar = directory / "client-1.20.1-20230612.114412-srg.jar"
    write_class_jar(slim_jar, [("d", "(Z)V")])
    write_class_jar(srg_jar, [("m_129985_", "(Z)V")])
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    version = make_version(game_arguments=["--fml.mcpVersion", "20230612.114412"])

    artifacts = LanAgentTargetResolver._find_forge_runtime_jars(version, "1.20.1")

    assert artifacts == (slim_jar, srg_jar)


def test_resolve_versions_before_117_returns_no_targets(tmp_path: Path) -> None:
    version = make_version()
    instance = make_instance(tmp_path, version_id="1.16.5")

    resolution = LanAgentTargetResolver.resolve(version, instance)

    assert resolution.targets == ()
    assert "1.17 or newer" in resolution.warnings[0]


def test_resolve_neoforge_emits_neoforge_srg_candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping_path = tmp_path / "client.txt"
    write_mojang_mappings(mapping_path)
    version = make_version(mapping_path, game_arguments=["--fml.neoFormVersion", "20240808.144430"])
    instance = make_instance(tmp_path, version_id="1.21.1", loader="neoforge")
    monkeypatch.setattr(LanAgentTargetResolver, "_ensure_client_mappings", classmethod(lambda cls, _version, _game_version, _reporter: mapping_path))
    monkeypatch.setattr(
        LanAgentTargetResolver,
        "_resolve_forge_srg_target",
        classmethod(lambda cls, _version, _game_version, _official: LanAgentTarget("forge-srg", "net/minecraft/server/MinecraftServer", "m_129985_")),
    )

    resolution = LanAgentTargetResolver.resolve(version, instance)

    assert resolution.loader == "neoforge"
    assert resolution.targets[0] == LanAgentTarget("neoforge-srg", "net/minecraft/server/MinecraftServer", "m_129985_")
    assert LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d") in resolution.targets


def test_find_neoforge_runtime_jars_uses_neoform_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "libraries" / "net/minecraft/client/1.21.1-20240808.144430"
    slim_jar = directory / "client-1.21.1-20240808.144430-slim.jar"
    srg_jar = directory / "client-1.21.1-20240808.144430-srg.jar"
    write_class_jar(slim_jar, [("d", "(Z)V")])
    write_class_jar(srg_jar, [("m_129985_", "(Z)V")])
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    version = make_version(game_arguments=["--fml.neoFormVersion", "20240808.144430"])

    artifacts = LanAgentTargetResolver._find_forge_runtime_jars(version, "1.21.1")

    assert artifacts == (slim_jar, srg_jar)


def write_quilt_hashed_v2(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        "tiny\t2\t0\tofficial\thashed\n"
        "c\tnet/minecraft/server/MinecraftServer\tnet/minecraft/unmapped/C_abcdef\n"
        "\tm\t(Z)V\td\tm_hashonline\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mappings/mappings.tiny", payload)


def test_parse_quilt_hashed_mapping(tmp_path: Path) -> None:
    mapping_jar = tmp_path / "hashed.jar"
    write_quilt_hashed_v2(mapping_jar)
    official = LanAgentTarget("official", "net/minecraft/server/MinecraftServer", "d")

    target = LanAgentTargetResolver._parse_quilt_hashed_mappings(mapping_jar, official)

    assert target == LanAgentTarget("quilt-hashed", "net/minecraft/unmapped/C_abcdef", "m_hashonline")


def test_resolve_quilt_falls_back_to_hashed_mappings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mapping_path = tmp_path / "client.txt"
    write_mojang_mappings(mapping_path)
    hashed_path = tmp_path / "libraries" / "org/quiltmc/hashed/1.20.1/hashed-1.20.1.jar"
    write_quilt_hashed_v2(hashed_path)
    version = make_version(mapping_path)
    version.libraries.append(
        {
            "name": "org.quiltmc:hashed:1.20.1",
            "downloads": {"artifact": {"path": "org/quiltmc/hashed/1.20.1/hashed-1.20.1.jar"}},
        }
    )
    instance = make_instance(tmp_path, loader="quilt")
    monkeypatch.setattr(Paths, "libraries", staticmethod(lambda: tmp_path / "libraries"))
    monkeypatch.setattr(LanAgentTargetResolver, "_ensure_client_mappings", classmethod(lambda cls, *_args: mapping_path))

    resolution = LanAgentTargetResolver.resolve(version, instance)

    assert resolution.loader == "quilt"
    assert resolution.targets[0] == LanAgentTarget("quilt-hashed", "net/minecraft/unmapped/C_abcdef", "m_hashonline")
    assert resolution.warnings == ()
