from __future__ import annotations

import argparse
from pathlib import Path
import sys

from mcw_core import CorePaths, LaunchRequest, MCWCore, ProgressEvent


def _progress(event: ProgressEvent) -> None:
    stage = event.stage.value
    if event.is_determinate:
        print(f"[{stage}] {event.message}: {event.current}/{event.total} ({event.percentage or 0:.1f}%)", flush=True)
    else:
        print(f"[{stage}] {event.message}", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Minecraft through the headless MCW Core public API.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="MCW data root containing instances/, cache/, and config/.")
    parser.add_argument("--instance", default="", help="Instance name to launch.")
    parser.add_argument("--username", default="MCWPlayer", help="Offline username used for the smoke launch.")
    parser.add_argument("--debug", action="store_true", help="Enable MinecraftExecutor debug output.")
    parser.add_argument("--list", action="store_true", help="List instances and exit without launching.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    core = MCWCore(CorePaths.from_root(args.root))

    if args.list:
        for instance in sorted(core.instances.list(), key=lambda item: item.name.casefold()):
            loader_name, loader_version = core.loaders.normalize(instance.mod_loader)
            loader = loader_name if loader_name == "vanilla" else f"{loader_name} {loader_version}"
            print(f"{instance.name}\tMinecraft {instance.version_id}\t{loader}")
        return 0

    if not args.instance.strip():
        _parser().error("--instance is required unless --list is used")

    core.operations.begin()
    try:
        result = core.launch(
            LaunchRequest(
                instance=args.instance.strip(),
                offline_username=args.username.strip(),
                debug_mode=bool(args.debug),
                on_progress=_progress,
            )
        )
    except KeyboardInterrupt:
        core.operations.cancel()
        print("Launch cancelled.", file=sys.stderr)
        return 130
    finally:
        core.operations.finish()

    print(f"Minecraft process started: {result.minecraft_version}")
    print(f"Java: {result.java_path} (compatibility target {result.minecraft_java_major_version})")
    for warning in result.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
