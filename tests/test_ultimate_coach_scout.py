"""Tests for the Ultimate Coach all-player scouting payload."""

from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.ultimate_coach_scout import build_scout_payload, catalog_scope_index
from database.engine import create_db_engine
from database.models import (
    Match,
    Player,
    PlayerHeadToHead,
    PlayerLeagueCareerStats,
    PlayerTeamHistory,
)


def _catalog():
    return {
        "schema": "ultimate-coach-historical-catalog-v2",
        "counts": {"sessions": 1, "divisions": 2},
        "source_limitations": ["old scoresheet unavailable"],
        "divisions": [
            {
                "division_id": "10",
                "catalog_session_name": "Fall 2026",
                "format": "EIGHT",
                "league_id": "1",
                "league_slug": "test",
            },
            {
                "division_id": "11",
                "catalog_session_name": "Fall 2026",
                "format": "NINE",
                "league_id": "1",
                "league_slug": "test",
            },
        ],
    }


def _add_game(db, match, a, b, a_result, fmt, a_sl, b_sl):
    db.add_all(
        [
            PlayerHeadToHead(
                player_id=a.id,
                opponent_id=b.id,
                match_id=match.id,
                result=a_result,
                own_skill_level=a_sl,
                opponent_skill_level=b_sl,
                format=fmt,
                session_name=match.session_name,
            ),
            PlayerHeadToHead(
                player_id=b.id,
                opponent_id=a.id,
                match_id=match.id,
                result="L" if a_result == "W" else "W",
                own_skill_level=b_sl,
                opponent_skill_level=a_sl,
                format=fmt,
                session_name=match.session_name,
            ),
        ]
    )


def test_current_sl_comes_from_current_membership_not_player_snapshot(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            player = Player(external_id="101", name="A", skill_level=2)
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="T1",
                    team_name="Team",
                    division_id="10",
                    session_name="Fall 2026",
                    is_current=True,
                    skill_level=5,
                )
            )
            db.commit()

            payload = build_scout_payload(db, catalog=_catalog())
            row = payload["players"][0]["formats"]["EIGHT"]

            assert row["display_skill_level"] == 5
            assert row["display_skill_level_status"] == "current_roster"
    finally:
        engine.dispose()


def test_historical_player_snapshot_is_not_mislabeled_current(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="101", name="A", skill_level=7)
            b = Player(external_id="102", name="B")
            db.add_all([a, b])
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=a.id,
                    team_external_id="OLD",
                    team_name="Old Team",
                    division_id="10",
                    session_name="Fall 2026",
                    is_current=False,
                    skill_level=3,
                )
            )
            match = Match(
                external_id="M1",
                match_date="2026-08-01T19:00:00-06:00",
                format="EIGHT",
                session_name="Fall 2026",
                is_scored=True,
                is_finalized=True,
            )
            db.add(match)
            db.flush()
            _add_game(db, match, a, b, "W", "EIGHT", 4, 5)
            db.commit()

            payload = build_scout_payload(db, catalog=_catalog())
            row = next(x for x in payload["players"] if x["name"] == "A")["formats"]["EIGHT"]

            assert row["display_skill_level"] == 4
            assert row["display_skill_level_status"] == "latest_observed"
            assert row["display_skill_level"] != 7
    finally:
        engine.dispose()


def test_formats_and_direct_opponents_are_kept_separate(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="101", name="A")
            b = Player(external_id="102", name="B")
            db.add_all([a, b])
            db.flush()
            eight = Match(
                external_id="M1",
                match_date="2026-08-01T19:00:00-06:00",
                format="EIGHT",
                session_name="Fall 2026",
                is_scored=True,
                is_finalized=True,
            )
            nine = Match(
                external_id="M2",
                match_date="2026-08-08T19:00:00-06:00",
                format="NINE",
                session_name="Fall 2026",
                is_scored=True,
                is_finalized=True,
            )
            db.add_all([eight, nine])
            db.flush()
            _add_game(db, eight, a, b, "W", "EIGHT", 4, 5)
            _add_game(db, nine, a, b, "L", "NINE", 4, 5)
            db.commit()

            payload = build_scout_payload(db, catalog=_catalog())
            row = next(x for x in payload["players"] if x["name"] == "A")
            assert row["formats"]["EIGHT"]["wins"] == 1
            assert row["formats"]["EIGHT"]["losses"] == 0
            assert row["formats"]["NINE"]["wins"] == 0
            assert row["formats"]["NINE"]["losses"] == 1
            assert row["formats"]["EIGHT"]["opponents"][str(b.id)]["games"] == 1
            assert row["formats"]["NINE"]["opponents"][str(b.id)]["games"] == 1
    finally:
        engine.dispose()


def test_scoresheet_only_identity_is_visible_but_not_default_selectable(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            player = Player(external_id="999", name="Unresolved")
            db.add(player)
            db.commit()

            payload = build_scout_payload(db, catalog=_catalog())
            row = payload["players"][0]
            assert row["identity_status"] == "scoresheet_only_or_unscoped"
            assert row["selectable_by_default"] is False
    finally:
        engine.dispose()


def test_league_scoped_career_stats_keep_source_alias(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            player = Player(external_id="101", name="A")
            db.add(player)
            db.flush()
            db.add(
                PlayerLeagueCareerStats(
                    player_id=player.id,
                    league_id="1",
                    league_slug="test",
                    alias_external_id="777",
                    format="EIGHT",
                    matches_won=12,
                    matches_played=20,
                    break_and_runs=3,
                )
            )
            db.commit()

            payload = build_scout_payload(db, catalog=_catalog())
            career = payload["players"][0]["career_stats"][0]
            assert career["alias_external_id"] == "777"
            assert career["win_rate"] == 0.6
            assert career["break_and_runs"] == 3
    finally:
        engine.dispose()


def test_conflicting_catalog_scope_is_not_used_for_current_format():
    catalog = _catalog()
    catalog["divisions"].append(
        {
            "division_id": "10",
            "catalog_session_name": "Fall 2026",
            "format": "NINE",
            "league_id": "1",
            "league_slug": "test",
        }
    )
    index, conflicts = catalog_scope_index(catalog)
    assert ("10", "Fall 2026") not in index
    assert len(conflicts) == 1
