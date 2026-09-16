"""Fail-closed tests for the Stage 1 pairing-evidence boundary."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics.head_to_head import skill_only_win_probability
from analytics.pairing_evidence import (
    EvidenceLabel,
    HeadToHeadGame,
    PairingEvidence,
    PairingEvidenceError,
    PairingReconciliationError,
    build_pairing_evidence_matrix,
    build_pairing_matrix,
    feasible_pairings,
)
from database.models import (
    Base,
    Match,
    Player,
    PlayerHeadToHead,
    PlayerTeamHistory,
)
from database.queries import CanonicalRosterError, canonical_current_roster


SESSION = "Fall 2026"
FORMAT = "EIGHT"
OUR_TEAM = "TEAM-OUR"
OPPONENT_TEAM = "TEAM-THEIRS"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _player(db, external_id: str, name: str) -> Player:
    row = Player(external_id=external_id, name=name)
    db.add(row)
    db.flush()
    return row


def _roster(
    db,
    player: Player,
    team_external_id: str,
    *,
    skill_level: int | None,
    session_name: str = SESSION,
    team_name: str | None = None,
    division_id: str = "DIV-1",
    is_current: bool = True,
) -> PlayerTeamHistory:
    row = PlayerTeamHistory(
        player_id=player.id,
        team_external_id=team_external_id,
        team_name=team_name or team_external_id,
        division_id=division_id,
        session_name=session_name,
        is_current=is_current,
        skill_level=skill_level,
    )
    db.add(row)
    db.flush()
    return row


def _match(
    db,
    external_id: str,
    *,
    format: str = FORMAT,
    session_name: str = SESSION,
    is_scored: bool = True,
    is_finalized: bool = True,
    is_bye: bool = False,
    home_team_id: str = OUR_TEAM,
    away_team_id: str = OPPONENT_TEAM,
) -> Match:
    row = Match(
        external_id=external_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        format=format,
        session_name=session_name,
        is_scored=is_scored,
        is_finalized=is_finalized,
        is_bye=is_bye,
    )
    db.add(row)
    db.flush()
    return row


def _game(
    db,
    player: Player,
    opponent: Player,
    match: Match,
    result: str | None,
    *,
    format: str | None = None,
    session_name: str | None = None,
    own_skill_level: int | None = 5,
    opponent_skill_level: int | None = 4,
) -> PlayerHeadToHead:
    row = PlayerHeadToHead(
        player_id=player.id,
        opponent_id=opponent.id,
        match_id=match.id,
        result=result,
        format=match.format if format is None else format,
        session_name=match.session_name if session_name is None else session_name,
        own_skill_level=own_skill_level,
        opponent_skill_level=opponent_skill_level,
    )
    db.add(row)
    db.flush()
    return row


def _seed_pair(db, *, our_skill: int | None = 5, opponent_skill: int | None = 4):
    player = _player(db, "P-OUR", "Our Player")
    opponent = _player(db, "P-OPP", "Opponent Player")
    _roster(db, player, OUR_TEAM, skill_level=our_skill)
    _roster(db, opponent, OPPONENT_TEAM, skill_level=opponent_skill)
    return player, opponent


def _build(db, **kwargs):
    return build_pairing_evidence_matrix(
        db,
        our_team_external_id=OUR_TEAM,
        opponent_team_external_id=OPPONENT_TEAM,
        format=FORMAT,
        session_name=SESSION,
        **kwargs,
    )


class TestAuthoritativeDirectEvidence:
    def test_finalized_scored_non_bye_result_is_direct(self, db):
        player, opponent = _seed_pair(db)
        match = _match(db, "M-1")
        _game(db, player, opponent, match, "W")

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.DIRECT
        assert evidence.observed_win_rate == 1.0
        assert evidence.direct_evidence_count == 1

    @pytest.mark.parametrize(
        "match_fields",
        [
            {"is_scored": False},
            {"is_finalized": False},
            {"is_bye": True},
        ],
    )
    def test_non_authoritative_match_state_never_counts_as_direct(self, db, match_fields):
        player, opponent = _seed_pair(db)
        match = _match(db, "M-BAD", **match_fields)
        _game(db, player, opponent, match, "W")

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.INDIRECT
        assert evidence.observed_win_rate is None
        assert evidence.direct_evidence_count == 0

    def test_unrecognized_result_never_counts_as_direct(self, db):
        player, opponent = _seed_pair(db)
        _game(db, player, opponent, _match(db, "M-UNKNOWN"), None)

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.INDIRECT
        assert evidence.direct_evidence_count == 0

    def test_direct_games_carries_the_real_dated_game_behind_the_pooled_count(self, db):
        """Match Night scouting card follow-up: direct_wins/direct_losses
        are a pooled count -- direct_games is the same real evidence,
        itemized with each real game's own date, never reconstructed or
        guessed."""
        player, opponent = _seed_pair(db)
        match = _match(db, "M-1")
        match.match_date = "2026-09-10"
        _game(db, player, opponent, match, "W")

        evidence = _build(db).pairings[0]

        assert evidence.direct_games == (HeadToHeadGame(match_date="2026-09-10", result="W"),)

    def test_direct_games_carries_a_missing_date_honestly(self, db):
        """A game with no recorded date must appear as None, never a
        guessed or reformatted value -- ordering itself is inherited
        unchanged from _authoritative_direct_rows's own existing query
        (SQL sorts NULL match_date first), not something this field
        changes or relies on being chronological."""
        player, opponent = _seed_pair(db)
        first = _match(db, "M-1")
        first.match_date = "2026-09-01"
        second = _match(db, "M-2")
        second.match_date = None
        _game(db, player, opponent, first, "W")
        _game(db, player, opponent, second, "L")

        evidence = _build(db).pairings[0]

        assert set(evidence.direct_games) == {
            HeadToHeadGame(match_date="2026-09-01", result="W"),
            HeadToHeadGame(match_date=None, result="L"),
        }

    def test_direct_games_is_empty_for_a_real_indirect_pairing(self, db):
        _seed_pair(db, our_skill=5, opponent_skill=4)

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.INDIRECT
        assert evidence.direct_games == ()

    def test_evidence_count_and_rate_use_distinct_matches(self, db):
        player, opponent = _seed_pair(db)
        first = _match(db, "M-1")
        _game(db, player, opponent, first, "W")
        _game(db, player, opponent, first, "W")
        _game(db, player, opponent, _match(db, "M-2"), "L")

        evidence = _build(db).pairings[0]

        assert evidence.direct_evidence_count == 2
        assert evidence.observed_win_rate == 0.5

    def test_direct_wins_and_losses_are_counted_exactly_not_reconstructed(self, db):
        """GPT audit follow-up (2026-09-16): a real 501-500 record rounds
        to observed_win_rate 0.500, which round(rate * count) reconstructs
        as the wrong 500-501. direct_wins/direct_losses must come from an
        exact count over the authoritative rows themselves, not the rate.
        This test uses a small stand-in (3 wins, 2 losses -> a rate that
        does not round back cleanly either) to prove the same principle
        without seeding 1001 real match rows."""
        player, opponent = _seed_pair(db)
        for i in range(3):
            _game(db, player, opponent, _match(db, f"M-W{i}"), "W")
        for i in range(2):
            _game(db, player, opponent, _match(db, f"M-L{i}"), "L")

        evidence = _build(db).pairings[0]

        assert evidence.direct_evidence_count == 5
        assert evidence.direct_wins == 3
        assert evidence.direct_losses == 2
        assert evidence.direct_wins + evidence.direct_losses == evidence.direct_evidence_count

    def test_conflicting_rows_in_one_match_fail_closed(self, db):
        player, opponent = _seed_pair(db)
        match = _match(db, "M-CONFLICT")
        _game(db, player, opponent, match, "W")
        _game(db, player, opponent, match, "L")

        with pytest.raises(PairingEvidenceError, match="Conflicting"):
            _build(db)

    def test_format_session_and_exact_opponent_are_owned_by_the_query(self, db):
        player, opponent = _seed_pair(db)
        other = _player(db, "P-OTHER", "Other Opponent")

        _game(db, player, other, _match(db, "M-OTHER"), "W")
        _game(
            db,
            player,
            opponent,
            _match(db, "M-OLD", session_name="Spring 2026"),
            "W",
        )
        _game(
            db,
            player,
            opponent,
            _match(db, "M-NINE", format="NINE"),
            "W",
        )
        _game(
            db,
            player,
            opponent,
            _match(
                db,
                "M-OTHER-TEAMS",
                home_team_id="TEAM-X",
                away_team_id="TEAM-Y",
            ),
            "W",
        )

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.INDIRECT
        assert evidence.direct_evidence_count == 0


class TestIndirectAndUnknownSemantics:
    def test_no_direct_history_with_real_skill_inputs_is_indirect(self, db):
        _seed_pair(db, our_skill=5, opponent_skill=4)

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.INDIRECT
        assert evidence.observed_win_rate is None
        assert evidence.modeled_win_probability == skill_only_win_probability(5, 4)
        assert evidence.model_source == "analytics.head_to_head:validated-skill-only"

    @pytest.mark.parametrize("our_skill,opponent_skill", [(None, 4), (5, None), (None, None)])
    def test_missing_model_input_is_unknown_not_neutral(self, db, our_skill, opponent_skill):
        _seed_pair(db, our_skill=our_skill, opponent_skill=opponent_skill)

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.UNKNOWN
        assert evidence.observed_win_rate is None
        assert evidence.modeled_win_probability is None
        assert evidence.model_source is None

    def test_unrelated_same_skill_history_is_not_an_indirect_proxy(self, db):
        player, opponent = _seed_pair(db, our_skill=5, opponent_skill=None)
        other = _player(db, "P-SAME-SL", "Same SL Elsewhere")
        match = _match(db, "M-SAME-SL")
        _game(db, player, other, match, "W", opponent_skill_level=4)

        evidence = _build(db).pairings[0]

        assert evidence.evidence_label is EvidenceLabel.UNKNOWN
        assert evidence.modeled_win_probability is None


class TestSideSpecificAvailability:
    def test_our_unavailability_never_removes_same_id_on_opponent_side(self):
        pairs = feasible_pairings(
            our_player_ids=[1, 2],
            opponent_player_ids=[2, 3],
            unavailable_our_player_ids={2},
            unavailable_opponent_player_ids=set(),
        )
        assert pairs == [(1, 2), (1, 3)]

    def test_each_side_can_be_filtered_independently(self):
        pairs = feasible_pairings(
            our_player_ids=[1, 2],
            opponent_player_ids=[10, 20],
            unavailable_our_player_ids={2},
            unavailable_opponent_player_ids={10},
        )
        assert pairs == [(1, 20)]

    def test_unknown_unavailable_id_is_rejected_by_production_builder(self, db):
        _seed_pair(db)
        with pytest.raises(PairingEvidenceError, match="not in the canonical roster"):
            _build(db, unavailable_our_player_ids={999})


def _evidence(player_id: int, opponent_id: int, label: EvidenceLabel) -> PairingEvidence:
    return PairingEvidence(
        player_id=player_id,
        player_external_id=f"P-{player_id}",
        player_name=f"Player {player_id}",
        player_skill_level=5,
        opponent_id=opponent_id,
        opponent_external_id=f"P-{opponent_id}",
        opponent_name=f"Opponent {opponent_id}",
        opponent_skill_level=4,
        format=FORMAT,
        session_name=SESSION,
        evidence_label=label,
        observed_win_rate=None,
        direct_evidence_count=0,
        modeled_win_probability=None,
        model_source=None,
    )


class TestExactFeasiblePairReconciliation:
    def test_complete_unique_matrix_reconciles(self):
        expected = [(1, 10), (1, 20), (2, 10)]
        rows = [
            _evidence(1, 10, EvidenceLabel.DIRECT),
            _evidence(1, 20, EvidenceLabel.INDIRECT),
            _evidence(2, 10, EvidenceLabel.UNKNOWN),
        ]
        assert build_pairing_matrix(rows, expected) == {
            "DIRECT": 1,
            "INDIRECT": 1,
            "UNKNOWN": 1,
            "total_feasible_pairings": 3,
        }

    def test_omission_is_rejected(self):
        with pytest.raises(PairingReconciliationError, match="missing keys"):
            build_pairing_matrix(
                [_evidence(1, 10, EvidenceLabel.DIRECT)],
                [(1, 10), (1, 20)],
            )

    def test_duplicate_plus_omission_is_rejected_even_when_totals_match(self):
        rows = [
            _evidence(1, 10, EvidenceLabel.DIRECT),
            _evidence(1, 10, EvidenceLabel.DIRECT),
        ]
        with pytest.raises(PairingReconciliationError) as excinfo:
            build_pairing_matrix(rows, [(1, 10), (1, 20)])
        assert "duplicate classified keys" in str(excinfo.value)
        assert "missing keys" in str(excinfo.value)

    def test_unexpected_key_is_rejected(self):
        with pytest.raises(PairingReconciliationError, match="unexpected keys"):
            build_pairing_matrix(
                [_evidence(1, 99, EvidenceLabel.UNKNOWN)],
                [(1, 10)],
            )

    def test_duplicate_expected_key_is_rejected(self):
        with pytest.raises(PairingReconciliationError, match="duplicate expected"):
            build_pairing_matrix(
                [_evidence(1, 10, EvidenceLabel.UNKNOWN)],
                [(1, 10), (1, 10)],
            )

    def test_production_builder_classifies_the_full_cross_product(self, db):
        ours = [_player(db, f"OUR-{i}", f"Our {i}") for i in range(2)]
        theirs = [_player(db, f"OPP-{i}", f"Opp {i}") for i in range(3)]
        for player in ours:
            _roster(db, player, OUR_TEAM, skill_level=5)
        for player in theirs:
            _roster(db, player, OPPONENT_TEAM, skill_level=4)

        matrix = _build(db)

        assert len(matrix.expected_pairings) == 6
        assert len(matrix.pairings) == 6
        assert matrix.counts == {
            "DIRECT": 0,
            "INDIRECT": 6,
            "UNKNOWN": 0,
            "total_feasible_pairings": 6,
        }


class TestCanonicalCurrentRoster:
    def test_immutable_team_id_not_mutable_name_selects_membership(self, db):
        first = _player(db, "P-1", "First")
        second = _player(db, "P-2", "Second")
        _roster(db, first, "TEAM-A", skill_level=4, team_name="Shared Name")
        _roster(db, second, "TEAM-B", skill_level=5, team_name="Shared Name")

        rows = canonical_current_roster(db, "TEAM-A", SESSION)

        assert [row.player_id for row in rows] == [first.id]

    def test_session_scope_is_mandatory_and_exact(self, db):
        player = _player(db, "P-1", "Player")
        _roster(db, player, OUR_TEAM, skill_level=4, session_name="Spring 2026")

        assert canonical_current_roster(db, OUR_TEAM, SESSION) == []
        with pytest.raises(ValueError, match="session_name"):
            canonical_current_roster(db, OUR_TEAM, "")

    def test_duplicate_current_membership_for_one_player_fails_closed(self, db):
        player = _player(db, "P-1", "Player")
        _roster(db, player, OUR_TEAM, skill_level=4, division_id="DIV-A")
        _roster(db, player, OUR_TEAM, skill_level=5, division_id="DIV-B")

        with pytest.raises(CanonicalRosterError, match="Multiple current roster rows"):
            canonical_current_roster(db, OUR_TEAM, SESSION)

    def test_no_current_membership_returns_empty_not_a_guess(self, db):
        player = _player(db, "P-1", "Player")
        _roster(db, player, OUR_TEAM, skill_level=4, is_current=False)

        assert canonical_current_roster(db, OUR_TEAM, SESSION) == []

    def test_same_player_on_both_sides_is_rejected(self, db):
        player = _player(db, "P-1", "Player")
        _roster(db, player, OUR_TEAM, skill_level=4)
        _roster(db, player, OPPONENT_TEAM, skill_level=4)

        with pytest.raises(PairingEvidenceError, match="both selected teams"):
            _build(db)
