from src.core.mod.provider_game_version_policy import provider_game_version_rank


def test_exact_provider_game_version_is_ranked_first() -> None:
    assert provider_game_version_rank("1.20.1", ("1.20.1", "1.20.4")) == 0


def test_nearby_patch_version_is_advisory_and_ranked_before_unknown() -> None:
    assert provider_game_version_rank("1.20.1", ("1.20.4",)) == 1
    assert provider_game_version_rank("1.20.1", ()) == 2


def test_unrelated_or_snapshot_labels_are_kept_as_low_priority() -> None:
    assert provider_game_version_rank("1.20.1", ("1.21.1",)) == 3
    assert provider_game_version_rank("1.20.1", ("24w14a",)) == 3
