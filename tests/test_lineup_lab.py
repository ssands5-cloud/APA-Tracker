"""Tests for analytics/lineup_lab.py (Stage 3).

The scoring formula and assignment rule are specified in
docs/stage3_lineup_lab_scoring.md -- these tests exist to hold the code to
that document, not to rediscover the design. Fixtures build
PairingEvidence/PairingEvidenceMatrix objects directly, the same real
dataclasses Stage 1 produces, following the pattern already established in
tests/test_captains_edge_summary.py and tests/test_lineup_risk.py.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from analytics.head_to_head import skill_only_win_probability
from analytics.lineup_lab import (
    MAX_ASSIGNMENT_ATTEMPTS,
    LineupLabError,
    pairing_score,
    solve,
)
from analytics.lineup_legality import TEAM_SKILL_LEVEL_LIMIT_5
from analytics.pairing_evidence import EvidenceLabel, PairingEvidence, PairingEvidenceMatrix


def _pairing(
    player_id, opponent_id, label, *,
    player_name=None, opponent_name=None,
    player_skill_level=5, opponent_skill_level=4,
    observed_win_rate=None, direct_evidence_count=0,
    modeled_win_probability=None, model_source=None,
):
    return PairingEvidence(
        player_id=player_id,
        player_external_id=f"P-{player_id}",
        player_name=player_name or f"Player {player_id}",
        player_skill_level=player_skill_level,
        opponent_id=opponent_id,
        opponent_external_id=f"OPP-{opponent_id}",
        opponent_name=opponent_name or f"Opponent {opponent_id}",
        opponent_skill_level=opponent_skill_level,
        format="8-Ball Open",
        session_name="Fall 2026",
        evidence_label=label,
        observed_win_rate=observed_win_rate,
        direct_evidence_count=direct_evidence_count,
        modeled_win_probability=modeled_win_probability,
        model_source=model_source,
    )


def _matrix(pairings):
    counts = {label.value: 0 for label in EvidenceLabel}
    for p in pairings:
        counts[p.evidence_label.value] += 1
    counts["total_feasible_pairings"] = len(pairings)
    return PairingEvidenceMatrix(
        our_team_external_id="OUR",
        opponent_team_external_id="THEIRS",
        format="8-Ball Open",
        session_name="Fall 2026",
        expected_pairings=tuple((p.player_id, p.opponent_id) for p in pairings),
        pairings=tuple(pairings),
        counts=counts,
        our_roster_available=True,
        opponent_roster_available=True,
    )


class TestPairingScore:
    def test_direct_and_indirect_use_the_same_validated_current_skill_score(self):
        direct = _pairing(1, 10, EvidenceLabel.DIRECT, modeled_win_probability=0.99,
                           model_source="analytics.head_to_head:direct-history-and-skill")
        indirect = _pairing(1, 11, EvidenceLabel.INDIRECT, modeled_win_probability=0.01,
                             model_source="analytics.head_to_head:validated-skill-only")
        expected = skill_only_win_probability(5, 4)
        assert pairing_score(direct) == expected
        assert pairing_score(indirect) == expected

    def test_unvalidated_direct_history_cannot_change_lineup_selection_score(self):
        win_history = _pairing(
            1, 10, EvidenceLabel.DIRECT, observed_win_rate=1.0,
            direct_evidence_count=10, modeled_win_probability=0.98,
        )
        loss_history = _pairing(
            1, 11, EvidenceLabel.DIRECT, observed_win_rate=0.0,
            direct_evidence_count=10, modeled_win_probability=0.02,
        )

        assert pairing_score(win_history) == pairing_score(loss_history)

    def test_unknown_scores_none_never_a_neutral_default(self):
        unknown = _pairing(1, 12, EvidenceLabel.UNKNOWN)
        assert pairing_score(unknown) is None

    @pytest.mark.parametrize(
        "player_skill_level,opponent_skill_level",
        [(None, 4), (5, None), (None, None)],
    )
    def test_missing_current_skill_input_is_unscoreable(
        self, player_skill_level, opponent_skill_level
    ):
        direct = _pairing(
            1,
            10,
            EvidenceLabel.DIRECT,
            player_skill_level=player_skill_level,
            opponent_skill_level=opponent_skill_level,
            modeled_win_probability=0.9,
        )
        assert pairing_score(direct) is None

    def test_regression_against_the_documented_worked_examples(self):
        assert round(skill_only_win_probability(5, 4), 3) == 0.599
        assert round(skill_only_win_probability(6, 3), 3) == 0.769
        assert skill_only_win_probability(6, 4) > skill_only_win_probability(5, 4)


class TestFullyScoreableLineup:
    def test_a_legal_five_a_side_matchup_is_fully_assigned(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.6,
                     player_skill_level=4, opponent_skill_level=4,
                     model_source="analytics.head_to_head:direct-history-and-skill")
            for p in range(1, 6) for o in range(10, 15)
        ]
        result = solve(_matrix(pairings))

        assert len(result.assignments) == 5
        assert result.unassigned_players == ()
        assert result.unassigned_opponents == ()
        assert result.is_legal is True
        assert result.skill_total == 20
        assert result.total_score == pytest.approx(2.5)
        assert result.blocked_reason is None

    def test_extra_available_players_are_left_unassigned_not_forced_in(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.6,
                     player_skill_level=4, opponent_skill_level=4)
            for p in range(1, 7) for o in range(10, 15)  # 6 of ours, 5 of theirs
        ]
        result = solve(_matrix(pairings))

        assert len(result.assignments) == 5
        assert len(result.unassigned_players) == 1
        assert result.unassigned_opponents == ()


class TestUnknownPairingsAreNeverGuessed:
    def test_a_player_with_only_unknown_edges_is_left_unassigned(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.6,
                     player_skill_level=4, opponent_skill_level=4)
            for p in range(1, 5) for o in range(10, 14)
        ]
        # Player 5 has no scoreable evidence against anyone.
        pairings += [_pairing(5, o, EvidenceLabel.UNKNOWN, player_skill_level=None)
                     for o in range(10, 14)]

        result = solve(_matrix(pairings))

        assigned_players = {slot.player_id for slot in result.assignments}
        assert 5 not in assigned_players
        assert any(u.player_id == 5 for u in result.unassigned_players)
        # Only 4 of ours had any real evidence at all -- a partial result,
        # not a fabricated 5th slot.
        assert len(result.assignments) == 4
        assert result.is_legal is None
        assert "Only 4 of 5" in result.blocked_reason

    def test_no_scoreable_pairing_at_all_is_a_clean_block(self):
        pairings = [_pairing(1, 10, EvidenceLabel.UNKNOWN, player_skill_level=None)]
        result = solve(_matrix(pairings))

        assert result.assignments == ()
        assert len(result.unassigned_players) == 1
        assert len(result.unassigned_opponents) == 1
        assert result.total_score is None
        assert result.is_legal is None
        assert result.blocked_reason is not None


class TestLegalityFallback:
    def _skewed_roster_matrix(self):
        """3 of ours at SL7 (score 0.90 vs everyone), 3 at SL2 (score 0.30),
        5 real identified opponents. The unconstrained best 5-lineup fields
        all three SL7 players (skill total 25, illegal); a legal 5-lineup
        exists at skill total 20 by fielding only two of the SL7 players.
        """
        strong = [(1, "A"), (2, "B"), (3, "C")]
        weak = [(4, "D"), (5, "E"), (6, "F")]
        pairings = []
        for pid, name in strong:
            for o in range(10, 15):
                pairings.append(_pairing(
                    pid, o, EvidenceLabel.DIRECT, player_name=name,
                    modeled_win_probability=0.90, player_skill_level=7,
                    opponent_skill_level=4,
                ))
        for pid, name in weak:
            for o in range(10, 15):
                pairings.append(_pairing(
                    pid, o, EvidenceLabel.DIRECT, player_name=name,
                    modeled_win_probability=0.30, player_skill_level=2,
                    opponent_skill_level=4,
                ))
        return _matrix(pairings)

    def test_an_illegal_max_score_lineup_falls_back_to_the_best_legal_one(self):
        result = solve(self._skewed_roster_matrix())

        assert result.is_legal is True
        assert result.skill_total <= TEAM_SKILL_LEVEL_LIMIT_5
        assert result.skill_total == 20
        expected = (
            2 * skill_only_win_probability(7, 4)
            + 3 * skill_only_win_probability(2, 4)
        )
        assert result.total_score == pytest.approx(expected)
        assert result.blocked_reason is None
        # Exactly two of the three SL7 players are fielded, never all three.
        strong_fielded = sum(1 for slot in result.assignments if slot.player_skill_level == 7)
        assert strong_fielded == 2

    def test_no_legal_five_lineup_is_reported_with_the_illegal_one_shown(self):
        # Every available player is SL7 -- any 5-player lineup totals 35,
        # always illegal. No fallback can exist.
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.8,
                     player_skill_level=7, opponent_skill_level=4)
            for p in range(1, 6) for o in range(10, 15)
        ]
        result = solve(_matrix(pairings))

        assert result.is_legal is False
        assert len(result.assignments) == 5
        assert result.skill_total == 35
        assert "No legal 5-player lineup" in result.blocked_reason


class TestReconciliation:
    def test_assigned_plus_unassigned_always_equals_available_on_both_sides(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.5,
                     player_skill_level=4, opponent_skill_level=4)
            for p in range(1, 8) for o in range(10, 16)
        ]
        result = solve(_matrix(pairings))

        our_ids = {p for p in range(1, 8)}
        opp_ids = {o for o in range(10, 16)}
        assigned_players = {slot.player_id for slot in result.assignments}
        assigned_opponents = {slot.opponent_id for slot in result.assignments}
        unassigned_players = {u.player_id for u in result.unassigned_players}
        unassigned_opponents = {u.opponent_id for u in result.unassigned_opponents}

        assert assigned_players | unassigned_players == our_ids
        assert assigned_players & unassigned_players == set()
        assert assigned_opponents | unassigned_opponents == opp_ids
        assert assigned_opponents & unassigned_opponents == set()

    def test_matrix_count_drift_fails_closed(self):
        pairings = [
            _pairing(1, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.5)
        ]
        matrix = _matrix(pairings)
        matrix.counts["INDIRECT"] = 99

        with pytest.raises(LineupLabError, match="stored counts"):
            solve(matrix)

    def test_matrix_scope_drift_fails_closed(self):
        pairing = replace(
            _pairing(1, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.5),
            session_name="Spring 2026",
        )

        with pytest.raises(LineupLabError, match="format/session scope"):
            solve(_matrix([pairing]))


class TestAvailability:
    def test_side_specific_unavailability_recomputes_the_assignment(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.INDIRECT, modeled_win_probability=0.5)
            for p in range(1, 4) for o in range(10, 13)
        ]

        result = solve(
            _matrix(pairings),
            unavailable_our_player_ids={1},
            unavailable_opponent_player_ids={10},
        )

        assert {slot.player_id for slot in result.assignments} <= {2, 3}
        assert {slot.opponent_id for slot in result.assignments} <= {11, 12}
        assert {u.player_id for u in result.unassigned_players} <= {2, 3}
        assert {u.opponent_id for u in result.unassigned_opponents} <= {11, 12}

    def test_unknown_unavailable_id_fails_closed(self):
        matrix = _matrix(
            [_pairing(1, 10, EvidenceLabel.INDIRECT, modeled_win_probability=0.5)]
        )
        with pytest.raises(LineupLabError, match="not in the evidence matrix"):
            solve(matrix, unavailable_our_player_ids={999})


class TestExactSearchBound:
    def test_a_roster_too_large_to_search_exactly_raises_rather_than_hangs(self):
        pairings = [
            _pairing(p, o, EvidenceLabel.DIRECT, modeled_win_probability=0.5,
                     player_skill_level=4, opponent_skill_level=4)
            for p in range(1, 10) for o in range(100, 109)  # 9 x 9
        ]
        import math
        assert math.comb(9, 5) * math.perm(9, 5) > MAX_ASSIGNMENT_ATTEMPTS

        with pytest.raises(LineupLabError, match="narrow tonight's availability"):
            solve(_matrix(pairings))

    def test_sparse_large_graph_is_bounded_after_maximum_matching(self):
        pairings = []
        for player_id in range(1, 14):
            for opponent_id in range(100, 113):
                if player_id == 1 and opponent_id == 100:
                    pairings.append(
                        _pairing(
                            player_id,
                            opponent_id,
                            EvidenceLabel.INDIRECT,
                            modeled_win_probability=0.5,
                        )
                    )
                else:
                    pairings.append(
                        _pairing(
                            player_id,
                            opponent_id,
                            EvidenceLabel.UNKNOWN,
                            player_skill_level=None,
                            opponent_skill_level=None,
                        )
                    )

        result = solve(_matrix(pairings))

        assert len(result.assignments) == 1
        assert "Only 1 of 5" in result.blocked_reason
