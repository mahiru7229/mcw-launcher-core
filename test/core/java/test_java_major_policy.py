import pytest

from src.core.java.java_major_policy import JavaMajorPolicy


def test_resolve_supported_buckets() -> None:
    assert JavaMajorPolicy.resolve(None) == 8
    assert JavaMajorPolicy.resolve(8) == 8
    assert JavaMajorPolicy.resolve(11) == 17
    assert JavaMajorPolicy.resolve(17) == 17
    assert JavaMajorPolicy.resolve(18) == 21
    assert JavaMajorPolicy.resolve(21) == 21
    assert JavaMajorPolicy.resolve(25) == 25


def test_rejects_newer_unsupported_java() -> None:
    with pytest.raises(RuntimeError):
        JavaMajorPolicy.resolve(26)


def test_java_21_is_a_managed_runtime_boundary() -> None:
    assert JavaMajorPolicy.SUPPORTED_MAJORS == (8, 17, 21, 25)
    assert JavaMajorPolicy.resolve(18) == 21
    assert JavaMajorPolicy.resolve(21) == 21
    assert JavaMajorPolicy.resolve(22) == 25


def test_accepted_majors_allow_metadata_major_and_compatibility_target() -> None:
    assert JavaMajorPolicy.accepted_majors(16) == (16, 17)
    assert JavaMajorPolicy.accepted_majors(17) == (17,)
    assert JavaMajorPolicy.accepted_majors(21) == (21,)
