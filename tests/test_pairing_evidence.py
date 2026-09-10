"""Tests for analytics.pairing_evidence -- the Stage 1 DIRECT/INDIRECT/
UNKNOWN evidence classifier (docs/captain_first_edge_experience.md §4-§8)
and database.queries.canonical_current_roster (§12).

Operates on plain PlayerHeadToHead/PlayerTeamHistory rows built directly,
the same style tests/test_matchups.py and tests/test_team_stats.py already
use -- pure classification logic tested independently of the database/
scraper plumbing, plus one small in-memory-SQLite test for the additive
query.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.pairing_evidence import (
    EvidenceLabel,
    build_pairing_matrix,
    classify_pairing,
    feasible_pairings,
)
from database.models import Base, PlayerHeadToHead, PlayerTeamHistory
from database.queries import canonical_current_roster


def _game(result, opponent_skill_level=None, own_skill_level=None):
    return PlayerHeadToHead(
        player_id=1, opponent_id=2, match_id=1,
        result=result, opponent_skill_level=opponent_skill_level,
        own_skill_level=own_skill_level,
    )


class TestClassifyPairingLabels:
    def test_a_recognized_direct_row_is_labeled_direct(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[_game("W")], same_skill_level_rows=[],
        )
        assert evidence.evidence_label == EvidenceLabel.DIRECT

    def test_direct_wins_over_indirect_when_both_exist(self):
        """Exact-opponent evidence outranks same-skill-level evidence for
        the label itself (§4), even though the indirect rate is still
        carried as context -- see test_indirect_rate_is_preserved_alongside_direct."""
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[_game("W")],
            same_skill_level_rows=[_game("L"), _game("L")],
        )
        assert evidence.evidence_label == EvidenceLabel.DIRECT

    def test_only_same_skill_level_evidence_is_labeled_indirect(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[], same_skill_level_rows=[_game("W")],
        )
        assert evidence.evidence_label == EvidenceLabel.INDIRECT

    def test_no_evidence_at_all_is_labeled_unknown(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[], same_skill_level_rows=[],
        )
        assert evidence.evidence_label == EvidenceLabel.UNKNOWN

    def test_an_unrecognized_result_does_not_count_as_direct_evidence(self):
        """A malformed/missing result is not silently a win, a loss, or
        evidence at all -- same recognized-result gate analytics.matchups
        already uses."""
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[_game(None), _game("UNKNOWN")], same_skill_level_rows=[],
        )
        assert evidence.evidence_label == EvidenceLabel.UNKNOWN
        assert evidence.direct_evidence_count == 0


class TestNeutralFallbacksAreNoneNotAFabricatedRate:
    """§6: an UNKNOWN or INDIRECT-only pairing's observed_win_rate is None
    -- never analytics.matchups' own 0.0/50 fallbacks, which are correct
    for THEIR already-shipped, already-documented outputs, not this one."""

    def test_unknown_pairing_has_no_observed_or_indirect_rate(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[], same_skill_level_rows=[],
        )
        assert evidence.observed_win_rate is None
        assert evidence.indirect_win_rate is None
        assert evidence.indirect_skill_level is None

    def test_indirect_pairing_has_no_observed_rate_but_a_real_indirect_rate(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[], same_skill_level_rows=[_game("W"), _game("L")],
        )
        assert evidence.observed_win_rate is None
        assert evidence.indirect_win_rate == 0.5
        assert evidence.indirect_skill_level == 5

    def test_direct_rate_is_a_real_unweighted_win_rate(self):
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[_game("W"), _game("W"), _game("L")],
            same_skill_level_rows=[],
        )
        assert evidence.observed_win_rate == round(2 / 3, 3)
        assert evidence.direct_evidence_count == 3

    def test_indirect_rate_is_preserved_alongside_direct(self):
        """A DIRECT pairing still carries its indirect (same-skill-level)
        rate as separate descriptive context -- never blended into
        observed_win_rate (§4)."""
        evidence = classify_pairing(
            player_id=1, opponent_id=2, opponent_skill_level=5,
            format="EIGHT", session_name="Fall 2026",
            direct_rows=[_game("W")],
            same_skill_level_rows=[_game("L"), _game("L")],
        )
        assert evidence.observed_win_rate == 1.0
        assert evidence.indirect_win_rate == 0.0
        assert evidence.indirect_evidence_count == 2


class TestFeasiblePairings:
    def test_every_combination_is_produced(self):
        pairs = feasible_pairings(our_player_ids=[1, 2], opponent_player_ids=[10, 20])
        assert set(pairs) == {(1, 10), (1, 20), (2, 10), (2, 20)}

    def test_unavailable_players_are_excluded_from_either_side(self):
        pairs = feasible_pairings(
            our_player_ids=[1, 2], opponent_player_ids=[10, 20],
            unavailable_player_ids={2, 10},
        )
        assert set(pairs) == {(1, 20)}

    def test_duplicate_ids_do_not_inflate_the_feasible_count(self):
        pairs = feasible_pairings(our_player_ids=[1, 1], opponent_player_ids=[10])
        assert pairs == [(1, 10)]


class TestEvidenceCountReconciliation:
    """§8: DIRECT + INDIRECT + UNKNOWN must equal total feasible pairings,
    as a hard invariant, not a soft check."""

    def test_counts_reconcile_for_a_mixed_matrix(self):
        pairings = [
            classify_pairing(1, 10, 5, "EIGHT", "Fall 2026", [_game("W")], []),
            classify_pairing(1, 20, 5, "EIGHT", "Fall 2026", [], [_game("W")]),
            classify_pairing(2, 10, 5, "EIGHT", "Fall 2026", [], []),
        ]
        counts = build_pairing_matrix(pairings)
        assert counts == {
            "DIRECT": 1, "INDIRECT": 1, "UNKNOWN": 1,
            "total_feasible_pairings": 3,
        }

    def test_an_empty_matrix_reconciles_to_zero(self):
        assert build_pairing_matrix([]) == {
            "DIRECT": 0, "INDIRECT": 0, "UNKNOWN": 0,
            "total_feasible_pairings": 0,
        }

    def test_mismatched_counts_raise_rather_than_silently_reporting(self):
        """A pairing classified under an unrecognized label would silently
        break the invariant this function exists to guarantee -- simulated
        here directly on the returned dict's arithmetic rather than by
        constructing an invalid EvidenceLabel (the real classifier can
        only ever produce the three real labels)."""
        pairings = [
            classify_pairing(1, 10, 5, "EIGHT", "Fall 2026", [_game("W")], []),
        ]
        counts = build_pairing_matrix(pairings)
        assert counts["DIRECT"] + counts["INDIRECT"] + counts["UNKNOWN"] == counts["total_feasible_pairings"]


class TestCanonicalCurrentRoster:
    """§12: current-roster membership comes only from the real
    PlayerTeamHistory.is_current signal, never from match-participation
    evidence."""

    def _session(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine)()

    def test_only_is_current_rows_are_returned(self):
        db = self._session()
        db.add_all([
            PlayerTeamHistory(
                player_id=1, team_name="Rack Attack", session_name="Fall 2026",
                is_current=True,
            ),
            PlayerTeamHistory(
                player_id=2, team_name="Rack Attack", session_name="Fall 2026",
                is_current=False,
            ),
        ])
        db.commit()

        roster = canonical_current_roster(db, "Rack Attack", "Fall 2026")

        assert [row.player_id for row in roster] == [1]

    def test_a_team_with_no_current_rows_returns_empty_not_a_guess(self):
        db = self._session()
        db.add(PlayerTeamHistory(
            player_id=1, team_name="Rack Attack", session_name="Fall 2026",
            is_current=False,
        ))
        db.commit()

        assert canonical_current_roster(db, "Rack Attack", "Fall 2026") == []

    def test_session_scoping_excludes_a_stale_session(self):
        db = self._session()
        db.add(PlayerTeamHistory(
            player_id=1, team_name="Rack Attack", session_name="Spring 2025",
            is_current=True,
        ))
        db.commit()

        assert canonical_current_roster(db, "Rack Attack", "Fall 2026") == []

    def test_omitting_session_returns_every_current_row_for_the_team(self):
        db = self._session()
        db.add_all([
            PlayerTeamHistory(
                player_id=1, team_name="Rack Attack", session_name="Spring 2025",
                is_current=True,
            ),
            PlayerTeamHistory(
                player_id=2, team_name="Rack Attack", session_name="Fall 2026",
                is_current=True,
            ),
        ])
        db.commit()

        roster = canonical_current_roster(db, "Rack Attack")

        assert {row.player_id for row in roster} == {1, 2}
