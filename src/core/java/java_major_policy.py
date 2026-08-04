class JavaMajorPolicy:
    SUPPORTED_MAJORS = (8, 17, 21, 25)

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
