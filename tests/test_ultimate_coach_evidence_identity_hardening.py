import pytest

from analytics.ultimate_coach_evidence_quality import direct_evidence, shared_opponent_evidence


@pytest.mark.parametrize("bad_id", [True, False, "1", 1.0, None])
def test_direct_evidence_rejects_noncanonical_player_identity(bad_id):
    with pytest.raises(ValueError, match="integer canonical player identity"):
        direct_evidence([], bad_id, 2, "EIGHT")


@pytest.mark.parametrize("bad_id", [True, False, "2", 2.0, None])
def test_direct_evidence_rejects_noncanonical_opponent_identity(bad_id):
    with pytest.raises(ValueError, match="integer canonical player identity"):
        direct_evidence([], 1, bad_id, "NINE")


@pytest.mark.parametrize("bad_id", [True, False, "1", 1.0, None])
def test_shared_opponent_evidence_rejects_noncanonical_identity(bad_id):
    with pytest.raises(ValueError, match="integer canonical player identity"):
        shared_opponent_evidence([], bad_id, 2, "EIGHT")


def test_integer_id_one_does_not_accept_bool_alias_as_public_identity():
    # Python considers True == 1. The public evidence API must not allow that
    # language-level alias to become an identity-resolution shortcut.
    with pytest.raises(ValueError):
        direct_evidence([], True, 2, "EIGHT")
    with pytest.raises(ValueError):
        shared_opponent_evidence([], 1, False, "NINE")
