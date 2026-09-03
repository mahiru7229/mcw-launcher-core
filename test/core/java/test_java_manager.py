from pathlib import Path
from types import SimpleNamespace

import pytest
import subprocess

from src.core.java.java_manager import JavaManager
from src.models.java.java import JavaInstallation
from src.models.java.java_source import JavaSource


@pytest.fixture(autouse=True)
def _emulate_windows_java_layout(monkeypatch: pytest.MonkeyPatch):
    """Keep historical Windows discovery cases deterministic on Linux CI."""
    monkeypatch.setattr(JavaManager, "_is_windows", lambda: True)


def make_java(
    version: int,
    executable: str,
    source: JavaSource,
) -> JavaInstallation:
    return JavaInstallation(
        version=version,
        executable=Path(executable),
        source=source,
    )


def test_linux_path_discovery_uses_java_from_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java = tmp_path / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"java")
    monkeypatch.setattr(JavaManager, "_is_windows", lambda: False)
    monkeypatch.setattr("src.core.java.java_manager.shutil.which", lambda name: str(java) if name == "java" else None)

    assert JavaManager._get_java_in_path() == [java]


def test_linux_java_home_uses_bin_java(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java_home = tmp_path / "jdk-21"
    java = java_home / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"java")
    monkeypatch.setattr(JavaManager, "_is_windows", lambda: False)
    monkeypatch.setenv("JAVA_HOME", str(java_home))

    assert JavaManager._get_java_in_java_home() == [java]


def test_find_installation_combines_all_sources(
    monkeypatch: pytest.MonkeyPatch,
):
    java_home = make_java(
        8,
        "java-home/javaw.exe",
        JavaSource.JAVA_HOME,
    )
    path_java = make_java(
        17,
        "path/javaw.exe",
        JavaSource.PATH,
    )
    program_files = make_java(
        21,
        "program-files/javaw.exe",
        JavaSource.PROGRAM_FILES,
    )
    registry = make_java(
        25,
        "registry/javaw.exe",
        JavaSource.REGISTRY,
    )
    managed_runtime = make_java(
        21,
        "runtimes/java-21/bin/javaw.exe",
        JavaSource.MINECRAFT_RUNTIME,
    )

    monkeypatch.setattr(
        JavaManager,
        "_scan_java_home",
        lambda: [java_home],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_path",
        lambda: [path_java],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_program_files",
        lambda: [program_files],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_registry",
        lambda: [registry],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_managed_runtimes",
        lambda: [managed_runtime],
    )
    monkeypatch.setattr(
        JavaManager,
        "_remove_duplicates",
        lambda javas: javas,
    )

    result = JavaManager.find_installation()

    assert result == [
        java_home,
        path_java,
        program_files,
        registry,
        managed_runtime,
    ]


def test_find_installation_passes_all_results_to_deduplication(
    monkeypatch: pytest.MonkeyPatch,
):
    found = [
        make_java(17, "a/javaw.exe", JavaSource.PATH),
        make_java(
            17,
            "b/javaw.exe",
            JavaSource.PROGRAM_FILES,
        ),
    ]
    received = {}

    monkeypatch.setattr(
        JavaManager,
        "_scan_java_home",
        lambda: [],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_path",
        lambda: [found[0]],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_program_files",
        lambda: [found[1]],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_registry",
        lambda: [],
    )
    monkeypatch.setattr(
        JavaManager,
        "_scan_managed_runtimes",
        lambda: [],
    )

    def fake_remove_duplicates(javas):
        received["javas"] = javas
        return ["deduplicated"]

    monkeypatch.setattr(
        JavaManager,
        "_remove_duplicates",
        fake_remove_duplicates,
    )

    result = JavaManager.find_installation()

    assert received["javas"] == found
    assert result == ["deduplicated"]


@pytest.mark.parametrize(
    (
        "scan_method",
        "path_method",
        "source",
    ),
    [
        (
            "_scan_java_home",
            "_get_java_in_java_home",
            JavaSource.JAVA_HOME,
        ),
        (
            "_scan_path",
            "_get_java_in_path",
            JavaSource.PATH,
        ),
        (
            "_scan_program_files",
            "_get_java_in_program_files",
            JavaSource.PROGRAM_FILES,
        ),
        (
            "_scan_registry",
            "_get_java_in_registry",
            JavaSource.REGISTRY,
        ),
        (
            "_scan_managed_runtimes",
            "_get_java_in_managed_runtimes",
            JavaSource.MINECRAFT_RUNTIME,
        ),
    ],
)
def test_scan_methods_use_expected_source(
    monkeypatch: pytest.MonkeyPatch,
    scan_method: str,
    path_method: str,
    source: JavaSource,
):
    java_path = Path("java/bin/javaw.exe")
    received = {}

    monkeypatch.setattr(
        JavaManager,
        path_method,
        lambda: [java_path],
    )

    def fake_scan_source(paths, received_source):
        received["paths"] = paths
        received["source"] = received_source
        return ["result"]

    monkeypatch.setattr(
        JavaManager,
        "_scan_source",
        fake_scan_source,
    )

    result = getattr(
        JavaManager,
        scan_method,
    )()

    assert result == ["result"]
    assert received == {
        "paths": [java_path],
        "source": source,
    }


def test_scan_source_returns_empty_list_for_none():
    assert (
        JavaManager._scan_source(
            None,
            JavaSource.PATH,
        )
        == []
    )


def test_scan_source_returns_empty_list_for_empty_paths():
    assert (
        JavaManager._scan_source(
            [],
            JavaSource.PATH,
        )
        == []
    )


def test_scan_source_creates_java_installations(
    monkeypatch: pytest.MonkeyPatch,
):
    java_8 = Path("java8/bin/javaw.exe")
    java_17 = Path("java17/bin/javaw.exe")

    versions = {
        java_8: 8,
        java_17: 17,
    }

    monkeypatch.setattr(
        JavaManager,
        "_get_major_version",
        lambda path: versions[path],
    )

    result = JavaManager._scan_source(
        [java_8, java_17],
        JavaSource.JAVA_HOME,
    )

    assert result == [
        JavaInstallation(
            version=8,
            executable=java_8,
            source=JavaSource.JAVA_HOME,
        ),
        JavaInstallation(
            version=17,
            executable=java_17,
            source=JavaSource.JAVA_HOME,
        ),
    ]


def test_scan_source_skips_none_paths(
    monkeypatch: pytest.MonkeyPatch,
):
    java_path = Path("java/bin/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "_get_major_version",
        lambda path: 17,
    )

    result = JavaManager._scan_source(
        [None, java_path],
        JavaSource.PATH,
    )

    assert result == [
        JavaInstallation(
            version=17,
            executable=java_path,
            source=JavaSource.PATH,
        )
    ]


def test_scan_source_skips_java_with_unknown_version(
    monkeypatch: pytest.MonkeyPatch,
):
    invalid = Path("invalid/javaw.exe")
    valid = Path("valid/javaw.exe")

    monkeypatch.setattr(
        JavaManager,
        "_get_major_version",
        lambda path: None if path == invalid else 21,
    )

    result = JavaManager._scan_source(
        [invalid, valid],
        JavaSource.PATH,
    )

    assert result == [
        JavaInstallation(
            version=21,
            executable=valid,
            source=JavaSource.PATH,
        )
    ]


def test_get_java_in_java_home_returns_none_when_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv(
        "JAVA_HOME",
        raising=False,
    )

    assert (
        JavaManager._get_java_in_java_home()
        is None
    )


def test_get_java_in_java_home_finds_standard_bin_layout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java_home = tmp_path / "jdk-21"
    executable = java_home / "bin" / "javaw.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")

    monkeypatch.setenv(
        "JAVA_HOME",
        str(java_home),
    )

    assert (
        JavaManager._get_java_in_java_home()
        == [executable]
    )


def test_get_java_in_java_home_accepts_bin_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java_bin = tmp_path / "jdk-17" / "bin"
    executable = java_bin / "javaw.exe"
    java_bin.mkdir(parents=True)
    executable.write_bytes(b"")

    monkeypatch.setenv(
        "JAVA_HOME",
        str(java_bin),
    )

    assert (
        JavaManager._get_java_in_java_home()
        == [executable]
    )


def test_get_java_in_java_home_returns_none_without_javaw(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java_home = tmp_path / "jdk"
    java_home.mkdir()

    monkeypatch.setenv(
        "JAVA_HOME",
        str(java_home),
    )

    assert (
        JavaManager._get_java_in_java_home()
        is None
    )


def test_get_java_in_path_converts_java_to_javaw_when_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java = tmp_path / "bin" / "java.exe"
    javaw = tmp_path / "bin" / "javaw.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")
    javaw.write_bytes(b"")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"{java}\n"
        ),
    )

    assert JavaManager._get_java_in_path() == [
        javaw
    ]


def test_get_java_in_path_keeps_java_when_javaw_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java = tmp_path / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"{java}\n"
        ),
    )

    assert JavaManager._get_java_in_path() == [
        java
    ]


def test_get_java_in_path_strips_blank_space(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    java = tmp_path / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=f"  {java}  \n"
        ),
    )

    assert JavaManager._get_java_in_path() == [
        java
    ]


def test_get_java_in_path_uses_where_with_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    received = {}

    def fake_run(command, **kwargs):
        received["command"] = command
        received["kwargs"] = kwargs
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run,
    )

    JavaManager._get_java_in_path()

    assert received["command"] == [
        "where",
        "java",
    ]
    assert received["kwargs"] == {
        "capture_output": True,
        "text": True,
        "check": True,
        "timeout": 8,
        "creationflags": JavaManager._creation_flags(),
    }


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(
            1,
            ["where", "java"],
        ),
        FileNotFoundError(),
        PermissionError(),
        OSError(),
    ],
)
def test_get_java_in_path_returns_none_on_scan_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
):
    def failing_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        subprocess,
        "run",
        failing_run,
    )

    assert (
        JavaManager._get_java_in_path()
        is None
    )


def test_get_java_in_path_returns_none_for_empty_output(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=""
        ),
    )

    assert (
        JavaManager._get_java_in_path()
        is None
    )


@pytest.mark.parametrize(
    (
        "version_output",
        "expected",
    ),
    [
        ('java version "1.8.0_491"\n', 8),
        ('openjdk version "17.0.12" 2024-07-16\n', 17),
        ('openjdk version "21" 2023-09-19 LTS\n', 21),
        ('java version "25.0.2" 2026-01-20\n', 25),
    ],
)
def test_get_major_version_parses_java_versions(
    monkeypatch: pytest.MonkeyPatch,
    version_output: str,
    expected: int,
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stderr=version_output
        ),
    )

    assert (
        JavaManager._get_major_version(
            Path("javaw.exe")
        )
        == expected
    )


def test_get_major_version_executes_requested_path(
    monkeypatch: pytest.MonkeyPatch,
):
    received = {}

    java_path = Path(
        "C:/Program Files/Java/bin/javaw.exe"
    )

    def fake_run(command, **kwargs):
        received["command"] = command
        received["kwargs"] = kwargs

        return SimpleNamespace(
            stderr='java version "17.0.1"\n'
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        fake_run,
    )

    result = JavaManager._get_major_version(
        java_path
    )

    assert result == 17

    assert received["command"] == [
        str(java_path),
        "-version",
    ]

    assert received["kwargs"] == {
        "capture_output": True,
        "text": True,
        "check": True,
        "timeout": 8,
        "creationflags": JavaManager._creation_flags(),
    }


def test_get_major_version_prefers_console_java_to_avoid_javaw_dialogs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    javaw_path = tmp_path / "broken-jre" / "bin" / "javaw.exe"
    java_path = javaw_path.with_name("java.exe")
    java_path.parent.mkdir(parents=True)
    javaw_path.write_bytes(b"")
    java_path.write_bytes(b"")
    received = {}

    def fake_run(command, **kwargs):
        received["command"] = command
        return SimpleNamespace(stderr='java version "1.8.0_502"\n')

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert JavaManager._get_major_version(javaw_path) == 8
    assert received["command"] == [str(java_path), "-version"]


@pytest.mark.parametrize(
    "version_output",
    [
        "",
        "OpenJDK Runtime Environment\n",
        "java version unknown\n",
    ],
)
def test_get_major_version_returns_none_for_unrecognized_output(
    monkeypatch: pytest.MonkeyPatch,
    version_output: str,
):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stderr=version_output
        ),
    )

    assert (
        JavaManager._get_major_version(
            Path("javaw.exe")
        )
        is None
    )


@pytest.mark.parametrize(
    "error",
    [
        subprocess.CalledProcessError(
            1,
            ["java", "-version"],
        ),
        FileNotFoundError(),
    ],
)
def test_get_major_version_returns_none_for_process_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
):
    def failing_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        subprocess,
        "run",
        failing_run,
    )

    assert (
        JavaManager._get_major_version(
            Path("javaw.exe")
        )
        is None
    )



def test_get_major_version_returns_none_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    def failing_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            ["java", "-version"],
            timeout=8,
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        failing_run,
    )

    result = JavaManager._get_major_version(
        Path("javaw.exe")
    )

    assert result is None


def test_get_program_files_dirs_reads_both_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "ProgramFiles",
        "C:/Program Files",
    )
    monkeypatch.setenv(
        "ProgramFiles(x86)",
        "C:/Program Files (x86)",
    )

    assert JavaManager._get_program_files_dirs() == [
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
    ]


def test_get_program_files_dirs_skips_missing_variables(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv(
        "ProgramFiles",
        raising=False,
    )
    monkeypatch.delenv(
        "ProgramFiles(x86)",
        raising=False,
    )

    assert JavaManager._get_program_files_dirs() == []


def test_get_java_in_program_files_scans_vendor_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    program_files = tmp_path / "Program Files"

    oracle_java = (
        program_files
        / "Java"
        / "jdk-21"
        / "bin"
        / "javaw.exe"
    )
    temurin_java = (
        program_files
        / "Eclipse Adoptium"
        / "jdk-17"
        / "bin"
        / "javaw.exe"
    )

    for executable in [
        oracle_java,
        temurin_java,
    ]:
        executable.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        executable.write_bytes(b"")

    monkeypatch.setattr(
        JavaManager,
        "_get_program_files_dirs",
        lambda: [program_files],
    )

    result = (
        JavaManager._get_java_in_program_files()
    )

    assert set(result) == {
        oracle_java,
        temurin_java,
    }


def test_get_java_in_program_files_ignores_missing_vendor_dirs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(
        JavaManager,
        "_get_program_files_dirs",
        lambda: [tmp_path],
    )

    assert (
        JavaManager._get_java_in_program_files()
        == []
    )


def test_remove_duplicates_keeps_one_java_per_major_version():
    result = JavaManager._remove_duplicates([
        make_java(
            8,
            "java8/javaw.exe",
            JavaSource.PATH,
        ),
        make_java(
            17,
            "java17/javaw.exe",
            JavaSource.PATH,
        ),
        make_java(
            21,
            "java21/javaw.exe",
            JavaSource.PATH,
        ),
    ])

    assert [
        java.version
        for java in result
    ] == [
        8,
        17,
        21,
    ]


@pytest.mark.parametrize(
    (
        "lower_source",
        "higher_source",
    ),
    [
        (
            JavaSource.PATH,
            JavaSource.REGISTRY,
        ),
        (
            JavaSource.REGISTRY,
            JavaSource.JAVA_HOME,
        ),
        (
            JavaSource.JAVA_HOME,
            JavaSource.PROGRAM_FILES,
        ),
    ],
)
def test_remove_duplicates_prefers_higher_priority_source(
    lower_source: JavaSource,
    higher_source: JavaSource,
):
    lower = make_java(
        17,
        "lower/javaw.exe",
        lower_source,
    )
    higher = make_java(
        17,
        "higher/javaw.exe",
        higher_source,
    )

    result = JavaManager._remove_duplicates([
        lower,
        higher,
    ])

    assert result == [higher]


def test_remove_duplicates_keeps_existing_java_on_equal_priority():
    first = make_java(
        17,
        "first/javaw.exe",
        JavaSource.PATH,
    )
    second = make_java(
        17,
        "second/javaw.exe",
        JavaSource.PATH,
    )

    result = JavaManager._remove_duplicates([
        first,
        second,
    ])

    assert result == [first]


def test_remove_duplicates_preserves_major_insertion_order():
    result = JavaManager._remove_duplicates([
        make_java(
            21,
            "java21/javaw.exe",
            JavaSource.PATH,
        ),
        make_java(
            8,
            "java8/javaw.exe",
            JavaSource.PATH,
        ),
        make_java(
            17,
            "java17/javaw.exe",
            JavaSource.PATH,
        ),
    ])

    assert [
        java.version
        for java in result
    ] == [
        21,
        8,
        17,
    ]


def test_remove_duplicates_documents_current_source_priority():
    sources = [
        JavaSource.PATH,
        JavaSource.REGISTRY,
        JavaSource.JAVA_HOME,
        JavaSource.PROGRAM_FILES,
    ]

    result = JavaManager._remove_duplicates([
        make_java(
            17,
            f"{source.value}/javaw.exe",
            source,
        )
        for source in sources
    ])

    assert result == [
        make_java(
            17,
            "PROGRAM_FILES/javaw.exe",
            JavaSource.PROGRAM_FILES,
        )
    ]

def test_find_installation_candidates_keeps_multiple_same_major_paths(monkeypatch: pytest.MonkeyPatch):
    java_home = JavaInstallation(version=17, executable=Path("C:/JavaA/bin/javaw.exe"), source=JavaSource.JAVA_HOME)
    managed = JavaInstallation(version=17, executable=Path("C:/JavaB/bin/javaw.exe"), source=JavaSource.MINECRAFT_RUNTIME)
    monkeypatch.setattr(JavaManager, "_scan_java_home", lambda: [java_home])
    monkeypatch.setattr(JavaManager, "_scan_path", lambda: [])
    monkeypatch.setattr(JavaManager, "_scan_program_files", lambda: [])
    monkeypatch.setattr(JavaManager, "_scan_registry", lambda: [])
    monkeypatch.setattr(JavaManager, "_scan_managed_runtimes", lambda: [managed])

    assert JavaManager.find_installation_candidates() == [java_home, managed]
    assert JavaManager.find_installation() == [managed]
