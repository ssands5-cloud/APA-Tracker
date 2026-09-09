"""Tests for the read-only Lineup Optimizer artifact builder."""

from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.lineup_optimizer import DEFAULT_WEIGHTS, LineupWeights
from database.models import Base, Player, PlayerH2HAdvantage, PlayerTrend, Team
from scripts.build_lineups import (
    build,
    build_payload,
    connect_read_only,
    fetch_pairing_rows,
    fetch_trends,
    load_weights_from_config,
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
