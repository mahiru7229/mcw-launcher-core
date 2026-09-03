from __future__ import annotations

import re


class JavaMajorPolicy:
    SUPPORTED_MAJORS = (8, 17, 21, 25)

    @classmethod
    def required_for_minecraft(cls, game_version: str, metadata_major: object = None) -> int:
        """Return the Java major required by a Minecraft version.

        Mojang's ``javaVersion`` metadata remains authoritative.  The release
        mapping is deliberately only a fallback for older/cached/custom
        profiles that do not carry that field; this is especially important
        while a Forge-family installer is preparing its launch profile.
        """
        if metadata_major not in (None, ""):
            try:
                required = int(metadata_major)
            except (TypeError, ValueError) as error:
                raise RuntimeError(f"Invalid Minecraft Java major version: {metadata_major!r}.") from error
            if required < 1:
                raise RuntimeError(f"Invalid Minecraft Java major version: {metadata_major!r}.")
            return required

        match = re.fullmatch(r"1\.(\d+)(?:\.(\d+))?", str(game_version or "").strip())
        if match is None:
            return 8
        minor = int(match.group(1))
        patch = int(match.group(2) or 0)
        if minor <= 16:
            return 8
        if minor == 17:
            return 16
        if minor < 20 or (minor == 20 and patch <= 4):
            return 17
        return 21

    @classmethod
    def resolve(cls, required_major: int | None) -> int:
        try:
            required = int(required_major or 8)
        except (TypeError, ValueError) as error:
            raise RuntimeError(f"Invalid Java major version: {required_major!r}.") from error

        for managed_major in cls.SUPPORTED_MAJORS:
            if required <= managed_major:
                return managed_major
        supported = ", ".join(str(major) for major in cls.SUPPORTED_MAJORS)
        raise RuntimeError(f"Java {required} is not supported. Supported managed runtimes: {supported}.")

    @classmethod
    def accepted_majors(cls, required_major: int | None) -> tuple[int, ...]:
        required = int(required_major or 8)
        managed = cls.resolve(required)
        return (required,) if required == managed else (required, managed)
