"""Tests for the pure Captain's Edge Summary rollup
(analytics/captains_edge_summary.py). Every input here mirrors the real
shape scripts.build_lineups.build_payload already produces -- this module
adds no new computation, only selection and ranking.
"""

from __future__ import annotations

from analytics.captains_edge_summary import (
    DEFAULT_TOP_N,
    build_captains_edge_summary,
    best_anchor_candidates,
    highest_risk_lineups,
    top_danger_matchups,
    top_strongest_pairings,
)


def pairing(player_name, opponent_name, matchup_score):
    return {"player_name": player_name, "opponent_name": opponent_name, "matchup_score": matchup_score}


def opponent(name, win_probability, volatility, danger):
    return {
        "opponent_name": name, "avg_win_probability": win_probability,
        "opponent_volatility": volatility, "is_danger_matchup": danger,
    }


def lineup(team, opponent_team, risk_score=None, anchor_name=None, anchor_stability=None):
    risk = None
    if risk_score is not None or anchor_name is not None:
        risk = {
            "lineup_risk_score": risk_score,
            "anchor_player_name": anchor_name,
            "anchor_stability_score": anchor_stability,
        }
    return {"team_name": team, "opponent_team_name": opponent_team, "lineup_risk": risk}


class TestTopStrongestPairings:
    def test_ranks_by_real_matchup_score_descending(self):
        pairings = [pairing("A", "X", 40), pairing("B", "Y", 90), pairing("C", "Z", 60)]
        top = top_strongest_pairings(pairings, n=2)
        assert [p.player_name for p in top] == ["B", "C"]

    def test_missing_matchup_score_is_excluded_not_ranked_as_zero(self):
        pairings = [pairing("A", "X", None), pairing("B", "Y", 10)]
        top = top_strongest_pairings(pairings)
        assert [p.player_name for p in top] == ["B"]

    def test_respects_n(self):
        pairings = [pairing(str(i), "X", i) for i in range(10)]
        assert len(top_strongest_pairings(pairings, n=3)) == 3

    def test_empty_input_is_empty(self):
        assert top_strongest_pairings([]) == []

    def test_default_n_matches_the_documented_value(self):
        assert DEFAULT_TOP_N == 5


class TestTopDangerMatchups:
    def test_only_real_flagged_danger_matchups_are_included(self):
        opponents = [
            opponent("Safe", 0.9, 0.1, False),
            opponent("Dangerous", 0.2, 0.5, True),
        ]
        result = top_danger_matchups(opponents)
        assert [o["opponent_name"] for o in result] == ["Dangerous"]

    def test_ranked_by_lowest_real_win_probability_first(self):
        opponents = [
            opponent("LessDangerous", 0.38, 0.5, True),
            opponent("MostDangerous", 0.10, 0.5, True),
        ]
        result = top_danger_matchups(opponents)
        assert [o["opponent_name"] for o in result] == ["MostDangerous", "LessDangerous"]

    def test_a_missing_win_probability_sorts_after_real_evidence(self):
        opponents = [
            opponent("NoEvidence", None, 0.9, True),
            opponent("RealEvidence", 0.30, 0.1, True),
        ]
        result = top_danger_matchups(opponents)
        assert [o["opponent_name"] for o in result] == ["RealEvidence", "NoEvidence"]

    def test_empty_input_is_empty(self):
        assert top_danger_matchups([]) == []


class TestBestAnchorCandidates:
    def test_ranks_by_real_anchor_stability_descending(self):
        lineups = [
            lineup("T1", "O1", anchor_name="Weak", anchor_stability=0.1),
            lineup("T1", "O2", anchor_name="Strong", anchor_stability=0.8),
        ]
        result = best_anchor_candidates(lineups)
        assert [c.player_name for c in result] == ["Strong", "Weak"]

    def test_a_lineup_with_no_real_anchor_is_excluded(self):
        lineups = [lineup("T1", "O1")]  # no risk block at all
        assert best_anchor_candidates(lineups) == []

    def test_carries_real_team_context(self):
        lineups = [lineup("Chalk It Up", "Corner Pockets", anchor_name="Alice", anchor_stability=0.5)]
        [candidate] = best_anchor_candidates(lineups)
        assert candidate.team_name == "Chalk It Up"
        assert candidate.opponent_team_name == "Corner Pockets"


class TestHighestRiskLineups:
    def test_ranks_by_real_lineup_risk_score_descending(self):
        lineups = [
            lineup("T1", "O1", risk_score=0.2, anchor_name="A"),
            lineup("T1", "O2", risk_score=0.9, anchor_name="B"),
        ]
        result = highest_risk_lineups(lineups)
        assert [l.opponent_team_name for l in result] == ["O2", "O1"]

    def test_a_lineup_with_no_risk_block_is_excluded(self):
        lineups = [{"team_name": "T1", "opponent_team_name": "O1"}]
        assert highest_risk_lineups(lineups) == []

    def test_empty_input_is_empty(self):
        assert highest_risk_lineups([]) == []


class TestBuildCaptainsEdgeSummary:
    def test_assembles_all_four_real_lists_from_one_document(self):
        document = {
            "pairings": [pairing("A", "X", 90)],
            "opponent_scouting": [opponent("Bob", 0.2, 0.6, True)],
            "lineups": [lineup("T1", "O1", risk_score=0.7, anchor_name="A", anchor_stability=0.6)],
        }
        summary = build_captains_edge_summary(document)
        assert len(summary.top_strongest_pairings) == 1
        assert len(summary.top_danger_matchups) == 1
        assert len(summary.best_anchor_candidates) == 1
        assert len(summary.highest_risk_lineups) == 1

    def test_missing_keys_produce_a_real_empty_summary_not_an_error(self):
        summary = build_captains_edge_summary({})
        assert summary.top_strongest_pairings == []
        assert summary.top_danger_matchups == []
        assert summary.best_anchor_candidates == []
        assert summary.highest_risk_lineups == []

    def test_a_custom_n_is_respected_across_every_list(self):
        document = {
            "pairings": [pairing(str(i), "X", i) for i in range(10)],
            "lineups": [
                lineup("T1", f"O{i}", risk_score=i, anchor_name=str(i), anchor_stability=i)
                for i in range(10)
            ],
        }
        summary = build_captains_edge_summary(document, n=2)
        assert len(summary.top_strongest_pairings) == 2
        assert len(summary.highest_risk_lineups) == 2
        assert len(summary.best_anchor_candidates) == 2
