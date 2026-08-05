from __future__ import annotations

from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import zipfile


ROOT = Path(__file__).resolve().parents[2]
TOOL_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = TOOL_ROOT / "src"
OUTPUT_JAR = ROOT / "runtime" / "mcw-lan-agent.jar"
MAIN_CLASS = "org.mcwlauncher.lanagent.McwLanAgent"


def run(command: list[str], cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def build() -> str:
    javac = shutil.which("javac")
    if javac is None:
        raise RuntimeError("javac was not found. Install a JDK to build the MCW LAN Agent.")

    sources = sorted(SOURCE_ROOT.rglob("*.java"))
    if not sources:
        raise RuntimeError("No Java agent sources were found.")

    OUTPUT_JAR.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mcw-lan-agent-") as temporary:
        temporary_root = Path(temporary)
        classes = temporary_root / "classes"
        classes.mkdir()
        run([javac, "--release", "8", "-encoding", "UTF-8", "-d", str(classes), *map(str, sources)])

        manifest = temporary_root / "MANIFEST.MF"
        manifest.write_text(
            "Manifest-Version: 1.0\n"
            f"Premain-Class: {MAIN_CLASS}\n"
            "Can-Redefine-Classes: false\n"
            "Can-Retransform-Classes: false\n\n",
            encoding="utf-8",
        )

        with zipfile.ZipFile(OUTPUT_JAR, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            write_deterministic(archive, "META-INF/MANIFEST.MF", manifest.read_bytes())
            for path in sorted(classes.rglob("*.class")):
                write_deterministic(archive, path.relative_to(classes).as_posix(), path.read_bytes())

    verify_agent(OUTPUT_JAR)
    digest = hashlib.sha256(OUTPUT_JAR.read_bytes()).hexdigest()
    print(f"Built {OUTPUT_JAR}")
    print(f"SHA-256: {digest}")
    return digest


def write_deterministic(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def verify_agent(agent_jar: Path) -> None:
    java = shutil.which("java")
    javac = shutil.which("javac")
    if java is None or javac is None:
        raise RuntimeError("java and javac are required for the agent verification test.")

    with tempfile.TemporaryDirectory(prefix="mcw-lan-agent-test-") as temporary:
        root = Path(temporary)
        server_source = root / "net" / "minecraft" / "server" / "MinecraftServer.java"
        server_source.parent.mkdir(parents=True)
        server_source.write_text(
            textwrap.dedent(
                """
                package net.minecraft.server;

                public final class MinecraftServer {
                    private boolean onlineMode;

                    public void setUsesAuthentication(boolean value) {
                        this.onlineMode = value;
                    }

                    public boolean usesAuthentication() {
                        return this.onlineMode;
                    }
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        main_source = root / "AgentSmokeTest.java"
        main_source.write_text(
            textwrap.dedent(
                """
                import net.minecraft.server.MinecraftServer;

                public final class AgentSmokeTest {
                    public static void main(String[] args) {
                        MinecraftServer server = new MinecraftServer();
                        server.setUsesAuthentication(true);
                        System.out.print(server.usesAuthentication());
                    }
                }
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        run([javac, "--release", "8", "-d", str(root), str(server_source), str(main_source)])

        normal = subprocess.run([java, "-cp", str(root), "AgentSmokeTest"], check=True, capture_output=True, text=True)
        if normal.stdout.strip() != "true":
            raise RuntimeError(f"Unexpected unpatched smoke-test output: {normal.stdout!r}")

        for loader in ("neoforge", "quilt"):
            agent_log = root / f"mcw-lan-agent-{loader}.log"
            patched = subprocess.run(
                [
                    java,
                    "-Dmcw.lan.offline=true",
                    f"-Dmcw.lan.loader={loader}",
                    "-Dmcw.lan.targets=net/minecraft/server/Wrong#missing;net/minecraft/server/MinecraftServer#setUsesAuthentication",
                    f"-Dmcw.lan.log={agent_log.as_posix()}",
                    f"-javaagent:{agent_jar}",
                    "-cp",
                    str(root),
                    "AgentSmokeTest",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            if patched.stdout.strip() != "false":
                raise RuntimeError(f"Agent smoke test failed for {loader}: stdout={patched.stdout!r}, stderr={patched.stderr!r}")
            if "patched net.minecraft.server.MinecraftServer#setUsesAuthentication(boolean)" not in patched.stderr:
                raise RuntimeError(f"Agent did not report a successful {loader} patch: {patched.stderr!r}")
            log_text = agent_log.read_text(encoding="utf-8")
            expected_log_messages = (
                "premain entered",
                f"loader={loader}",
                "enabled with 2 resolved target candidate(s)",
                "candidate: net.minecraft.server.MinecraftServer#setUsesAuthentication(boolean)",
                "target class loaded by",
                "patched net.minecraft.server.MinecraftServer#setUsesAuthentication(boolean)",
                "shutdown summary: LAN Offline Mode patch was applied successfully",
            )
            missing = [message for message in expected_log_messages if message not in log_text]
            if missing:
                raise RuntimeError(f"Dedicated {loader} agent log is incomplete; missing={missing!r}, log={log_text!r}")



if __name__ == "__main__":
    try:
        build()
    except Exception as error:
        print(f"Agent build failed: {error}", file=sys.stderr)
        raise
