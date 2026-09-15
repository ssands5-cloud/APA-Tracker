"""Tests for analytics/player_vs_player_matrix.py.

Builds real PairingEvidence/PairingEvidenceMatrix fixtures (Stage 1's own
shape) and real PlayerHeadToHead histories, and asserts the combined export
row never drops a pairing, never forces direct_matches and total_games to
agree, and never blends the four separate probability/rate fields into a
new score.
"""

from __future__ import annotations

from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix
from analytics.player_vs_player_matrix import (
    UNAVAILABLE_FIELDS,
    build_matrix_export,
    rows_for_player,
)
from database.models import PlayerHeadToHead


def _pairing(player_id, opponent_id, label, *, player_name=None, opponent_name=None,
             player_skill_level=5, opponent_skill_level=4, observed_win_rate=None,
             direct_evidence_count=0, modeled_win_probability=None, model_source=None,
             format="8-Ball Open", session_name="Fall 2026"):
    return PairingEvidence(
        player_id=player_id, player_external_id=f"P-{player_id}",
        player_name=player_name or f"Player {player_id}", player_skill_level=player_skill_level,
        opponent_id=opponent_id, opponent_external_id=f"OPP-{opponent_id}",
        opponent_name=opponent_name or f"Opponent {opponent_id}",
        opponent_skill_level=opponent_skill_level, format=format, session_name=session_name,
        evidence_label=label, observed_win_rate=observed_win_rate,
        direct_evidence_count=direct_evidence_count,
        modeled_win_probability=modeled_win_probability, model_source=model_source,
    )


def _matrix(pairings, *, format="8-Ball Open", session_name="Fall 2026"):
    counts = {label.value: 0 for label in EvidenceLabel}
    for p in pairings:
        counts[p.evidence_label.value] += 1
    counts["total_feasible_pairings"] = len(pairings)
    return PairingEvidenceMatrix(
        our_team_external_id="OUR", opponent_team_external_id="THEIRS",
        format=format, session_name=session_name,
        expected_pairings=tuple((p.player_id, p.opponent_id) for p in pairings),
        pairings=tuple(pairings), counts=counts,
        our_roster_available=True, opponent_roster_available=True,
    )


def _game(player_id=1, opponent_id=10, result="W", own=5, opp=4, match_id=1):
    return PlayerHeadToHead(
        player_id=player_id, opponent_id=opponent_id, match_id=match_id, result=result,
        own_skill_level=own, opponent_skill_level=opp,
        format="8-Ball Open", session_name="Fall 2026",
    )


class TestEveryPairingIsRepresented:
    def test_no_pairing_is_dropped_regardless_of_evidence_label(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1),
            _pairing(1, 11, EvidenceLabel.INDIRECT, modeled_win_probability=0.6,
                     model_source="analytics.head_to_head:validated-skill-only"),
            _pairing(2, 10, EvidenceLabel.UNKNOWN, player_skill_level=None),
        ]
        rows = build_matrix_export(_matrix(pairings), histories={})

        assert len(rows) == 3
        assert {(r.player_id, r.opponent_id) for r in rows} == {(1, 10), (1, 11), (2, 10)}

    def test_an_unknown_pairing_with_no_history_gets_an_honest_empty_summary(self):
        pairings = [_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)]
        [row] = build_matrix_export(_matrix(pairings), histories={})

        assert row.summary.total_games == 0
        assert row.summary.modeled_win_probability is None
        assert row.summary.games == ()
        assert row.evidence_label is EvidenceLabel.UNKNOWN


class TestDirectMatchesNeverForcedEqualToTotalGames:
    def test_the_two_counts_are_carried_through_independently(self):
        pairing = _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=2,
                            observed_win_rate=1.0)
        # Deliberately supply a DIFFERENT number of history rows than
        # Stage 1's own distinct-match count, to prove this module does not
        # cross-check or force the two to agree -- they come from separate
        # real sources answering separate real questions.
        histories = {(1, 10): [_game(match_id=1)]}
        [row] = build_matrix_export(_matrix([pairing]), histories)

        assert row.direct_matches == 2
        assert row.summary.total_games == 1
        assert row.observed_win_rate == 1.0


class TestNoNewBlending:
    def test_the_four_separate_fields_are_never_combined_into_a_new_score(self):
        pairing = _pairing(1, 10, EvidenceLabel.DIRECT, direct_evidence_count=1,
                            observed_win_rate=1.0)
        histories = {(1, 10): [_game(match_id=1)]}
        [row] = build_matrix_export(_matrix([pairing]), histories)

        # Each of these is independently inspectable; none is None simply
        # because another was populated, and none is derived from another.
        assert row.observed_win_rate == 1.0
        assert row.summary.reliability == 0.25
        assert row.summary.skill_only_probability is not None
        assert row.summary.modeled_win_probability is not None
        assert row.summary.skill_only_probability != row.summary.modeled_win_probability

    def test_unavailable_fields_are_disclosed_on_every_row(self):
        pairings = [_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)]
        [row] = build_matrix_export(_matrix(pairings), histories={})

        assert row.unavailable_fields == UNAVAILABLE_FIELDS
        assert any("innings" in f for f in row.unavailable_fields)
        assert any("break_run_rate" in f for f in row.unavailable_fields)
        assert any("volatility" in f for f in row.unavailable_fields)


class TestStructuralOrdering:
    def test_format_orders_eight_ball_before_nine_ball(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.UNKNOWN, format="9-Ball Open", player_skill_level=None),
            _pairing(1, 10, EvidenceLabel.UNKNOWN, format="8-Ball Open", player_skill_level=None),
        ]
        # Two different formats for the "same" pair id-wise is artificial
        # for a single real matrix, but the sort function must not care --
        # it only reads matrix.format per constructed row via the matrix
        # itself, so build two single-pairing matrices and compare rows.
        eight = build_matrix_export(_matrix([pairings[1]], format="8-Ball Open"), {})
        nine = build_matrix_export(_matrix([pairings[0]], format="9-Ball Open"), {})
        combined = sorted(eight + nine, key=lambda r: (r.format,))
        # Direct structural check via the module's own sort applied to a
        # mixed list built by hand:
        from analytics.player_vs_player_matrix import _sort_key
        ordered = sorted(eight + nine, key=_sort_key)
        assert ordered[0].format == "8-Ball Open"
        assert ordered[1].format == "9-Ball Open"

    def test_player_name_orders_case_insensitively(self):
        pairings = [
            _pairing(2, 10, EvidenceLabel.UNKNOWN, player_name="zoe", player_skill_level=None),
            _pairing(1, 10, EvidenceLabel.UNKNOWN, player_name="Adam", player_skill_level=None),
        ]
        rows = build_matrix_export(_matrix(pairings), {})
        assert [r.player_name for r in rows] == ["Adam", "zoe"]

    def test_opponent_name_breaks_a_tie_on_player_name(self):
        pairings = [
            _pairing(1, 11, EvidenceLabel.UNKNOWN, player_name="Adam",
                     opponent_name="Zed", player_skill_level=None),
            _pairing(1, 10, EvidenceLabel.UNKNOWN, player_name="Adam",
                     opponent_name="Ann", player_skill_level=None),
        ]
        rows = build_matrix_export(_matrix(pairings), {})
        assert [r.opponent_name for r in rows] == ["Ann", "Zed"]


class TestRowsForPlayer:
    def test_returns_only_that_players_rows_in_stable_order(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.UNKNOWN, opponent_name="Bob", player_skill_level=None),
            _pairing(1, 11, EvidenceLabel.UNKNOWN, opponent_name="Ann", player_skill_level=None),
            _pairing(2, 10, EvidenceLabel.UNKNOWN, player_skill_level=None),
        ]
        rows = build_matrix_export(_matrix(pairings), {})
        player_1_rows = rows_for_player(rows, 1)

        assert {r.opponent_id for r in player_1_rows} == {10, 11}
        assert [r.opponent_name for r in player_1_rows] == ["Ann", "Bob"]
