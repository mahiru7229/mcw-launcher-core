from src.core.minecraft.classpath_builder import ClasspathBuilder
from src.core.minecraft.argument_builder import ArgumentBuilder
from src.core.modloader.forge.forge_launch_command_manager import ForgeLaunchCommandManager
from src.models.minecraft.version import Version
from src.core.fs.paths import Paths
from src.models.instance.settings import InstanceSettings
from src.models.account.account import Account


class LauncherManager:
    CLASSPATH_FLAGS = ("-cp", "-classpath", "--class-path")

    @staticmethod
    def build(version: Version, context: dict, settings: InstanceSettings, account: Account, runtime_jvm_arguments: list[str] | None = None) -> list[str]:
        classpath = ClasspathBuilder.build(
            version,
            Paths.client(version),
            Paths.libraries(),
        )

        jvm_args, game_args = ArgumentBuilder.build(version, context, settings, account)
        jvm_args = ForgeLaunchCommandManager.prepare(version, jvm_args, client_path=Paths.client(version), library_directory=Paths.libraries())
        if runtime_jvm_arguments:
            jvm_args.extend(str(argument) for argument in runtime_jvm_arguments)

        command = list(jvm_args)
        if not LauncherManager._has_classpath_argument(command):
            command.extend(["-cp", classpath])
        command.extend([version.main_class, *game_args])
        return command

    @classmethod
    def _has_classpath_argument(cls, arguments: list[str]) -> bool:
        for value in arguments:
            if value in cls.CLASSPATH_FLAGS:
                return True
            if value.startswith("--class-path="):
                return True
        return False
