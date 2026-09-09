"""Tests for the read-only Lineup Optimizer artifact builder."""

from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.lineup_optimizer import DEFAULT_WEIGHTS, LineupWeights
from analytics.lineup_risk import DEFAULT_LINEUP_RISK_WEIGHTS, LineupRiskWeights
from analytics.opponent_scouting import (
    DEFAULT_OPPONENT_SCOUTING_THRESHOLDS,
    OpponentScoutingThresholds,
)
from analytics.win_probability import DEFAULT_WIN_PROBABILITY_WEIGHTS, WinProbabilityWeights
from database.models import Base, Player, PlayerH2HAdvantage, PlayerHeadToHead, PlayerTrend, Team
from scripts.build_lineups import (
    build,
    build_payload,
    connect_read_only,
    fetch_pairing_rows,
    fetch_trends,
    fetch_win_rates_by_skill_level,
    load_lineup_risk_weights_from_config,
    load_opponent_scouting_thresholds_from_config,
    load_weights_from_config,
    load_win_probability_weights_from_config,
    write_lineups_json,
)


@pytest.fixture
def db_path(tmp_path):
    """A complete 2x2 matchup with one trend row intentionally absent."""

    path = tmp_path / "apa.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        own_team = Team(external_id="T1", name="Chalk It Up")
        opponent_team = Team(external_id="T2", name="Corner Pockets")
        alice = Player(external_id="P1", name="Alice", skill_level=5, team=own_team)
        alex = Player(external_id="P2", name="Alex", skill_level=4, team=own_team)
        bob = Player(external_id="P3", name="Bob", skill_level=5, team=opponent_team)
        carol = Player(external_id="P4", name="Carol", skill_level=6, team=opponent_team)
        db.add_all([own_team, opponent_team, alice, alex, bob, carol])
        db.flush()

        # The best whole-lineup assignment is Alice -> Bob and Alex -> Carol,
        # not the two independently strongest cells for Alice/Alex.
        db.add_all([
            PlayerH2HAdvantage(
                player_id=alice.id, opponent_id=bob.id, matchup_score=90,
                win_probability=0.90, expected_points=3.0, format="8-Ball Open",
                session_name="Summer 2026",
            ),
            PlayerH2HAdvantage(
                player_id=alice.id, opponent_id=carol.id, matchup_score=80,
                win_probability=0.80, expected_points=2.0, format="8-Ball Open",
                session_name="Summer 2026",
            ),
            PlayerH2HAdvantage(
                player_id=alex.id, opponent_id=bob.id, matchup_score=85,
                win_probability=0.85, expected_points=2.5, format="8-Ball Open",
                session_name="Summer 2026",
            ),
            PlayerH2HAdvantage(
                player_id=alex.id, opponent_id=carol.id, matchup_score=70,
                win_probability=0.70, expected_points=1.0, format="8-Ball Open",
                session_name="Summer 2026",
            ),
        ])
        db.add_all([
            PlayerTrend(
                player_id=alice.id, format="8-ball", session_name="Summer 2026",
                sample_size=8, current_skill_level=5, regression_slope=0.05,
                volatility=0.2, sl_stability=0.83, hot_cold_flag="HOT",
            ),
            # Alex has no matching trend row, which must remain null in the
            # exported evidence rather than becoming 0.
        ])
        db.commit()

    engine.dispose()
    return path


@pytest.fixture
def connection(db_path):
    conn = connect_read_only(db_path)
    yield conn
    conn.close()


class TestReadOnlySource:
    def test_fetches_real_rows_and_trends(self, connection):
        rows = fetch_pairing_rows(connection)
        trends = fetch_trends(connection)
        assert len(rows) == 4
        assert rows[0]["player_name"] == "Alex"
        assert rows[0]["matchup_score"] == 85
        assert rows[0]["team_name"] == "Chalk It Up"
        assert len(trends) == 1

    def test_source_connection_rejects_writes(self, connection):
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM player_h2h_advantage")


class TestPayload:
    def test_solves_one_to_one_lineup_and_keeps_raw_values(self, connection, db_path):
        payload = build_payload(connection, source_db=str(db_path))

        assert payload["schema_version"] == 1
        assert payload["source_db"] == str(db_path.resolve())
        assert payload["pairing_rows"] == 4
        assert len(payload["pairings"]) == 4
        assert len(payload["lineups"]) == 1

        lineup = payload["lineups"][0]
        assert lineup["team_name"] == "Chalk It Up"
        assert lineup["opponent_team_name"] == "Corner Pockets"
        assert lineup["roster_resolution"] == "team_id"
        assert lineup["players_considered"] == 2
        assert lineup["opponents_considered"] == 2
        assert len(lineup["assignments"]) == 2
        assert len({row["opponent_id"] for row in lineup["assignments"]}) == 2
        assert lineup["objective_total"] > 0

        alice = next(row for row in lineup["assignments"] if row["player_name"] == "Alice")
        assert alice["source_pairing"] is True
        assert alice["matchup_score_raw"] in {80, 90}
        assert alice["matchup_score"] == pytest.approx(alice["matchup_score_raw"] / 100)
        first_pairing = payload["pairings"][0]
        assert first_pairing["team_pk_raw"] == first_pairing["team_pk"]
        assert first_pairing["opponent_team_pk_raw"] == first_pairing["opponent_team_pk"]

        alex = next(row for row in lineup["assignments"] if row["player_name"] == "Alex")
        assert alex["confidence"] is None
        assert alex["risk_factor"] is None
        assert any("no matching player trend" in warning for warning in payload["resolution_warnings"])

    def test_unresolved_opponent_team_is_not_fabricated_into_a_lineup(self, tmp_path):
        path = tmp_path / "unresolved.db"
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            team = Team(external_id="T1", name="Only Team")
            player = Player(external_id="P1", name="Alice", team=team)
            opponent = Player(external_id="P2", name="Unknown Opponent")
            db.add_all([team, player, opponent])
            db.flush()
            db.add(PlayerH2HAdvantage(
                player_id=player.id, opponent_id=opponent.id, matchup_score=50,
                win_probability=0.5, format="8-Ball Open", session_name="Summer 2026",
            ))
            db.commit()
        engine.dispose()

        conn = connect_read_only(path)
        try:
            payload = build_payload(conn, source_db=str(path))
        finally:
            conn.close()
        assert payload["pairing_rows"] == 1
        assert payload["lineups"] == []
        assert payload["pairings"][0]["lineup_eligible"] is False
        assert any("own or opponent team" in warning for warning in payload["resolution_warnings"])

    def test_missing_h2h_edge_is_explicit_and_uses_neutral_arithmetic(self, tmp_path):
        path = tmp_path / "sparse.db"
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            own = Team(external_id="T1", name="Own")
            opp = Team(external_id="T2", name="Opp")
            alice = Player(external_id="P1", name="Alice", team=own)
            alex = Player(external_id="P2", name="Alex", team=own)
            bob = Player(external_id="P3", name="Bob", team=opp)
            carol = Player(external_id="P4", name="Carol", team=opp)
            db.add_all([own, opp, alice, alex, bob, carol])
            db.flush()
            db.add_all([
                PlayerH2HAdvantage(
                    player_id=alice.id, opponent_id=bob.id, matchup_score=60,
                    win_probability=0.6, format="8-Ball Open", session_name="Summer 2026",
                ),
                PlayerH2HAdvantage(
                    player_id=alex.id, opponent_id=carol.id, matchup_score=60,
                    win_probability=0.6, format="8-Ball Open", session_name="Summer 2026",
                ),
            ])
            db.commit()
        engine.dispose()

        conn = connect_read_only(path)
        try:
            payload = build_payload(conn, source_db=str(path))
        finally:
            conn.close()
        assignments = payload["lineups"][0]["assignments"]
        assert len(assignments) == 2
        assert any("no H2H row" in warning for warning in payload["resolution_warnings"])

    def test_old_empty_database_is_safe(self, tmp_path):
        path = tmp_path / "old.db"
        sqlite3.connect(path).close()
        conn = connect_read_only(path)
        try:
            payload = build_payload(conn, source_db=str(path))
        finally:
            conn.close()
        assert payload["pairing_rows"] == 0
        assert payload["lineups"] == []
        assert payload["resolution_warnings"]


class TestConfiguredWeights:
    """apa_config.yaml's real `lineup_optimizer` section, threaded through
    load_weights_from_config -> build_payload -> the real PairingCandidate
    matrix -- see docs/lineup_optimizer.md and
    analytics.lineup_optimizer.LineupWeights."""

    def test_a_missing_section_falls_back_to_the_original_defaults(self):
        assert load_weights_from_config({}) == DEFAULT_WEIGHTS
        assert load_weights_from_config(None) == DEFAULT_WEIGHTS

    def test_an_empty_section_falls_back_to_the_original_defaults(self):
        assert load_weights_from_config({"lineup_optimizer": {}}) == DEFAULT_WEIGHTS

    def test_a_partial_override_only_changes_the_keys_it_names(self):
        weights = load_weights_from_config({"lineup_optimizer": {"weight_matchup_score": 0.9}})
        assert weights.matchup_score == 0.9
        assert weights.win_probability == DEFAULT_WEIGHTS.win_probability
        assert weights.confidence == DEFAULT_WEIGHTS.confidence
        assert weights.risk_penalty == DEFAULT_WEIGHTS.risk_penalty

    def test_a_full_override_matches_every_configured_value(self):
        weights = load_weights_from_config({
            "lineup_optimizer": {
                "weight_matchup_score": 0.10,
                "weight_win_probability": 0.20,
                "weight_confidence": 0.30,
                "weight_risk_penalty": 0.40,
            }
        })
        assert weights == LineupWeights(
            matchup_score=0.10, win_probability=0.20, confidence=0.30, risk_penalty=0.40,
        )

    def test_custom_weights_reach_the_real_payloads_objective_total(self, connection, db_path):
        """End-to-end proof the override isn't silently dropped somewhere
        in build_payload's own matrix construction -- the same real
        database, scored two different real ways, must disagree."""
        default_payload = build_payload(connection, source_db=str(db_path))
        matchup_only = LineupWeights(
            matchup_score=1.0, win_probability=0.0, confidence=0.0, risk_penalty=0.0,
        )
        custom_payload = build_payload(connection, source_db=str(db_path), weights=matchup_only)

        default_total = default_payload["lineups"][0]["objective_total"]
        custom_total = custom_payload["lineups"][0]["objective_total"]
        assert custom_total != default_total


class TestWinRatesBySkillLevel:
    """fetch_win_rates_by_skill_level -- WR_SL for analytics.win_probability:
    real win rate vs opponents sharing a skill level, grouped by that
    skill level, not by specific opponent identity (that's the existing
    real win_probability/WR_H2H, unchanged)."""

    @pytest.fixture
    def db_with_head_to_head(self, tmp_path):
        path = tmp_path / "h2h.db"
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            team = Team(external_id="T1", name="Chalk It Up")
            opp_team = Team(external_id="T2", name="Corner Pockets")
            alice = Player(external_id="P1", name="Alice", skill_level=5, team=team)
            bob = Player(external_id="P2", name="Bob", skill_level=4, team=opp_team)
            carol = Player(external_id="P3", name="Carol", skill_level=4, team=opp_team)
            dave = Player(external_id="P4", name="Dave", skill_level=6, team=opp_team)
            db.add_all([team, opp_team, alice, bob, carol, dave])
            db.flush()

            from database.models import Match
            matches = [Match(external_id=f"M{i}", is_scored=True, is_finalized=True) for i in range(4)]
            db.add_all(matches)
            db.flush()

            # Alice vs two real SL4 opponents (Bob, Carol): 1 win, 1 loss.
            # Alice vs one real SL6 opponent (Dave): 1 win.
            db.add_all([
                PlayerHeadToHead(player_id=alice.id, opponent_id=bob.id, match_id=matches[0].id,
                                 own_skill_level=5, opponent_skill_level=4, result="W"),
                PlayerHeadToHead(player_id=alice.id, opponent_id=carol.id, match_id=matches[1].id,
                                 own_skill_level=5, opponent_skill_level=4, result="L"),
                PlayerHeadToHead(player_id=alice.id, opponent_id=dave.id, match_id=matches[2].id,
                                 own_skill_level=5, opponent_skill_level=6, result="W"),
            ])
            db.commit()
            alice_pk = alice.id  # captured before the session closes below
        engine.dispose()
        conn = connect_read_only(path)
        yield conn, alice_pk
        conn.close()

    def test_win_rate_is_grouped_by_opponent_skill_level_not_identity(self, db_with_head_to_head):
        conn, alice_pk = db_with_head_to_head
        rates = fetch_win_rates_by_skill_level(conn)
        assert rates[(alice_pk, 4)] == pytest.approx(0.5)  # 1 win / 2 games vs real SL4 opponents
        assert rates[(alice_pk, 6)] == pytest.approx(1.0)  # 1 win / 1 game vs the real SL6 opponent

    def test_a_skill_level_with_no_real_games_is_absent_not_zero(self, db_with_head_to_head):
        conn, alice_pk = db_with_head_to_head
        rates = fetch_win_rates_by_skill_level(conn)
        assert (alice_pk, 2) not in rates

    def test_no_table_at_all_is_empty_not_an_error(self, tmp_path):
        path = tmp_path / "empty.db"
        sqlite3.connect(path).close()
        conn = connect_read_only(path)
        try:
            assert fetch_win_rates_by_skill_level(conn) == {}
        finally:
            conn.close()


class TestConfiguredWinProbabilityWeights:
    """apa_config.yaml's real `win_probability` section, threaded through
    load_win_probability_weights_from_config -> build_payload -> every
    real PairingCandidate's modeled_win_probability."""

    def test_a_missing_section_falls_back_to_the_original_defaults(self):
        assert load_win_probability_weights_from_config({}) == DEFAULT_WIN_PROBABILITY_WEIGHTS
        assert load_win_probability_weights_from_config(None) == DEFAULT_WIN_PROBABILITY_WEIGHTS

    def test_a_partial_override_only_changes_the_keys_it_names(self):
        weights = load_win_probability_weights_from_config(
            {"win_probability": {"weight_sl_delta": 0.9}}
        )
        assert weights.sl_delta == 0.9
        assert weights.wr_sl == DEFAULT_WIN_PROBABILITY_WEIGHTS.wr_sl
        assert weights.wr_h2h == DEFAULT_WIN_PROBABILITY_WEIGHTS.wr_h2h
        assert weights.volatility == DEFAULT_WIN_PROBABILITY_WEIGHTS.volatility
        assert weights.logistic_scale == DEFAULT_WIN_PROBABILITY_WEIGHTS.logistic_scale
        assert weights.clamp_min == DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_min
        assert weights.clamp_max == DEFAULT_WIN_PROBABILITY_WEIGHTS.clamp_max

    def test_a_full_override_matches_every_configured_value(self):
        weights = load_win_probability_weights_from_config({
            "win_probability": {
                "weight_sl_delta": 0.1, "weight_wr_sl": 0.2, "weight_wr_h2h": 0.3,
                "weight_volatility": 0.4, "logistic_scale": 2.0,
                "clamp_min": 0.05, "clamp_max": 0.95,
            }
        })
        assert weights == WinProbabilityWeights(
            sl_delta=0.1, wr_sl=0.2, wr_h2h=0.3, volatility=0.4,
            logistic_scale=2.0, clamp_min=0.05, clamp_max=0.95,
        )

    def test_modeled_win_probability_appears_on_every_real_assignment(self, connection, db_path):
        """Alice (SL5) vs Bob (SL5, even) and Alex (SL4) vs Carol (SL6,
        disadvantaged) -- real skill levels from the db_path fixture --
        confirms modeled_win_probability is computed and threaded all the
        way into the real payload, not just accepted and dropped."""
        payload = build_payload(connection, source_db=str(db_path))
        assignments = payload["lineups"][0]["assignments"]
        assert len(assignments) == 2
        for row in assignments:
            assert row["modeled_win_probability"] is not None
            assert 0.0 < row["modeled_win_probability"] < 1.0

    def test_custom_weights_change_the_real_modeled_win_probability(self, connection, db_path):
        default_payload = build_payload(connection, source_db=str(db_path))
        sl_only = WinProbabilityWeights(sl_delta=5.0, wr_sl=0.0, wr_h2h=0.0, volatility=0.0)
        custom_payload = build_payload(
            connection, source_db=str(db_path), win_probability_weights=sl_only,
        )

        def by_pair(payload):
            return {
                (row["player_name"], row["opponent_name"]): row["modeled_win_probability"]
                for row in payload["lineups"][0]["assignments"]
            }

        assert by_pair(default_payload) != by_pair(custom_payload)


class TestLineupRiskInThePayload:
    """analytics.lineup_risk computed once per solved lineup and stored on
    the real lineup payload -- no new artifact, no new solver, just an
    extra key on the block scripts.build_lineups already writes."""

    def test_a_missing_section_falls_back_to_the_original_defaults(self):
        assert load_lineup_risk_weights_from_config({}) == DEFAULT_LINEUP_RISK_WEIGHTS
        assert load_lineup_risk_weights_from_config(None) == DEFAULT_LINEUP_RISK_WEIGHTS

    def test_a_partial_override_only_changes_the_keys_it_names(self):
        weights = load_lineup_risk_weights_from_config(
            {"lineup_risk": {"weight_upset_risk": 0.9}}
        )
        assert weights.upset_risk == 0.9
        assert weights.anchor_instability == DEFAULT_LINEUP_RISK_WEIGHTS.anchor_instability
        assert weights.volatility_load == DEFAULT_LINEUP_RISK_WEIGHTS.volatility_load
        assert weights.danger_count == DEFAULT_LINEUP_RISK_WEIGHTS.danger_count
        assert weights.danger_threshold == DEFAULT_LINEUP_RISK_WEIGHTS.danger_threshold

    def test_a_full_override_matches_every_configured_value(self):
        weights = load_lineup_risk_weights_from_config({
            "lineup_risk": {
                "weight_upset_risk": 0.1, "weight_anchor_instability": 0.2,
                "weight_volatility_load": 0.3, "weight_danger_count": 0.4,
                "danger_threshold": 0.55,
            }
        })
        assert weights == LineupRiskWeights(
            upset_risk=0.1, anchor_instability=0.2, volatility_load=0.3,
            danger_count=0.4, danger_threshold=0.55,
        )

    def test_every_real_lineup_carries_a_complete_risk_block(self, connection, db_path):
        payload = build_payload(connection, source_db=str(db_path))
        lineup = payload["lineups"][0]
        risk = lineup["lineup_risk"]
        assert set(risk) == {
            "upset_risk_index", "anchor_stability_score", "anchor_player_name",
            "lineup_volatility_load", "danger_matchup_count", "lineup_risk_score",
            "rationale",
        }
        assert isinstance(risk["danger_matchup_count"], int)
        assert isinstance(risk["lineup_risk_score"], float)
        assert isinstance(risk["rationale"], str) and risk["rationale"]
        # The db_path fixture's real anchor: Alice and Alex are the two
        # assigned players, and the risk block must name one of them --
        # never a player who isn't in this lineup.
        assert risk["anchor_player_name"] in {"Alice", "Alex"}

    def test_custom_weights_change_the_real_lineup_risk_score(self, connection, db_path):
        default_payload = build_payload(connection, source_db=str(db_path))
        danger_only = LineupRiskWeights(
            upset_risk=0.0, anchor_instability=0.0, volatility_load=0.0,
            danger_count=10.0, danger_threshold=0.99,
        )
        custom_payload = build_payload(
            connection, source_db=str(db_path), lineup_risk_weights=danger_only,
        )
        default_score = default_payload["lineups"][0]["lineup_risk"]["lineup_risk_score"]
        custom_score = custom_payload["lineups"][0]["lineup_risk"]["lineup_risk_score"]
        assert custom_score != default_score
        # danger_threshold=0.99 means every real assignment counts as a
        # danger matchup -- 2 assignments * weight 10.0.
        assert custom_score == pytest.approx(20.0)


class TestOpponentScoutingInThePayload:
    """analytics.opponent_scouting, wired from the same real eligible
    pairing rows and trends the Lineup Optimizer already fetches -- no new
    database query, no new artifact type."""

    def test_a_missing_section_falls_back_to_the_original_defaults(self):
        assert load_opponent_scouting_thresholds_from_config({}) == DEFAULT_OPPONENT_SCOUTING_THRESHOLDS
        assert load_opponent_scouting_thresholds_from_config(None) == DEFAULT_OPPONENT_SCOUTING_THRESHOLDS

    def test_a_partial_override_only_changes_the_keys_it_names(self):
        thresholds = load_opponent_scouting_thresholds_from_config(
            {"opponent_scouting": {"win_probability_danger_threshold": 0.25}}
        )
        assert thresholds.win_probability_danger == 0.25
        assert thresholds.volatility_danger == DEFAULT_OPPONENT_SCOUTING_THRESHOLDS.volatility_danger

    def test_a_full_override_matches_every_configured_value(self):
        thresholds = load_opponent_scouting_thresholds_from_config({
            "opponent_scouting": {
                "win_probability_danger_threshold": 0.3,
                "volatility_danger_threshold": 0.6,
            }
        })
        assert thresholds == OpponentScoutingThresholds(win_probability_danger=0.3, volatility_danger=0.6)

    def test_every_real_opponent_the_lineup_faced_appears_in_scouting(self, connection, db_path):
        payload = build_payload(connection, source_db=str(db_path))
        scouted_names = {entry["opponent_name"] for entry in payload["opponent_scouting"]}
        # db_path's real opponents are Bob and Carol.
        assert scouted_names == {"Bob", "Carol"}

    def test_a_real_entry_carries_every_expected_key(self, connection, db_path):
        payload = build_payload(connection, source_db=str(db_path))
        entry = payload["opponent_scouting"][0]
        assert set(entry) == {
            "opponent_id", "opponent_name", "opponent_team_id", "opponent_team_name",
            "times_faced", "avg_matchup_score", "avg_win_probability",
            "opponent_volatility", "is_danger_matchup", "danger_reasons",
        }

    def test_custom_thresholds_change_which_real_opponents_are_flagged(self, connection, db_path):
        lenient = OpponentScoutingThresholds(win_probability_danger=0.0, volatility_danger=1.1)
        strict = OpponentScoutingThresholds(win_probability_danger=1.0, volatility_danger=-1.0)
        lenient_payload = build_payload(connection, source_db=str(db_path), opponent_scouting_thresholds=lenient)
        strict_payload = build_payload(connection, source_db=str(db_path), opponent_scouting_thresholds=strict)

        assert all(not e["is_danger_matchup"] for e in lenient_payload["opponent_scouting"])
        assert all(e["is_danger_matchup"] for e in strict_payload["opponent_scouting"])


class TestArtifact:
    def test_atomic_writer_replaces_stale_output(self, tmp_path):
        path = tmp_path / "exports" / "lineups.json"
        path.parent.mkdir()
        path.write_text('{"stale": true}\n', encoding="utf-8")
        result = write_lineups_json({"schema_version": 1, "lineups": []}, path)
        assert result == path
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "schema_version": 1,
            "lineups": [],
        }
        assert not list(path.parent.glob(".lineups.json.*.tmp"))

    def test_build_replaces_stale_json_with_current_database(self, db_path, tmp_path):
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        output = out_dir / "lineups.json"
        output.write_text('{"stale": true}\n', encoding="utf-8")
        assert build(str(db_path), str(out_dir)) == output
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["pairing_rows"] == 4
        assert "stale" not in payload
