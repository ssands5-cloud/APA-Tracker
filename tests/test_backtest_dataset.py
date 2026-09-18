"""Regression tests for leakage-safe backtest examples."""

from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.backtest_dataset import build_backtest_examples
from database.engine import create_db_engine
from database.models import Match, Player, PlayerHeadToHead


def _add_game(db, match, a, b, a_result, fmt="EIGHT", a_sl=4, b_sl=5):
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


def test_second_match_sees_first_but_first_sees_no_future(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            db.add_all([a, b])
            db.flush()
            m1 = Match(external_id="101", match_date="2024-01-01T19:00:00-07:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            m2 = Match(external_id="102", match_date="2024-02-01T19:00:00-07:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            db.add_all([m1, m2])
            db.flush()
            _add_game(db, m1, a, b, "W")
            _add_game(db, m2, a, b, "L")
            db.commit()

            rows = build_backtest_examples(db)
            assert len(rows) == 2
            assert rows[0].direct_games_before == 0
            assert rows[0].direct_win_rate_before is None
            assert rows[1].direct_games_before == 1
            assert rows[1].direct_win_rate_before == 1.0
    finally:
        engine.dispose()


def test_same_team_match_does_not_leak_between_slots(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            c = Player(external_id="3", name="C")
            db.add_all([a, b, c])
            db.flush()
            match = Match(external_id="101", match_date="2024-01-01T19:00:00-07:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            db.add(match)
            db.flush()
            _add_game(db, match, a, b, "W")
            _add_game(db, match, a, c, "L")
            db.commit()

            rows = build_backtest_examples(db)
            assert len(rows) == 2
            assert all(row.player_games_before == 0 for row in rows)
            assert all(row.shared_opponent_count_before == 0 for row in rows)
    finally:
        engine.dispose()


def test_shared_opponent_only_uses_prior_matches(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            shared = Player(external_id="3", name="Shared")
            db.add_all([a, b, shared])
            db.flush()
            dates = ["2024-01-01T19:00:00-07:00", "2024-02-01T19:00:00-07:00", "2024-03-01T19:00:00-07:00"]
            matches = [
                Match(external_id=str(101+i), match_date=date, format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
                for i, date in enumerate(dates)
            ]
            db.add_all(matches)
            db.flush()
            _add_game(db, matches[0], a, shared, "W", a_sl=4, b_sl=4)
            _add_game(db, matches[1], b, shared, "L", a_sl=5, b_sl=4)
            _add_game(db, matches[2], a, b, "W", a_sl=4, b_sl=5)
            db.commit()

            rows = build_backtest_examples(db)
            target = next(row for row in rows if row.match_external_id == "103")
            assert target.shared_opponent_count_before == 1
            assert target.player_shared_games_before == 1
            assert target.player_shared_win_rate_before == 1.0
            assert target.opponent_shared_games_before == 1
            assert target.opponent_shared_win_rate_before == 0.0
    finally:
        engine.dispose()


def test_formats_never_cross_contaminate(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            db.add_all([a, b])
            db.flush()
            eight = Match(external_id="101", match_date="2024-01-01T19:00:00-07:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            nine = Match(external_id="102", match_date="2024-02-01T19:00:00-07:00", format="NINE", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            db.add_all([eight, nine])
            db.flush()
            _add_game(db, eight, a, b, "W", fmt="EIGHT")
            _add_game(db, nine, a, b, "L", fmt="NINE")
            db.commit()

            rows = build_backtest_examples(db)
            nine_row = next(row for row in rows if row.format == "NINE")
            assert nine_row.direct_games_before == 0
    finally:
        engine.dispose()


def test_same_timestamp_across_different_matches_is_one_withheld_batch(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            c = Player(external_id="3", name="C")
            db.add_all([a, b, c])
            db.flush()
            when = "2024-01-01T19:00:00-07:00"
            m1 = Match(external_id="101", match_date=when, format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            m2 = Match(external_id="102", match_date=when, format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            db.add_all([m1, m2])
            db.flush()
            _add_game(db, m1, a, b, "W")
            _add_game(db, m2, a, c, "L")
            db.commit()

            rows = build_backtest_examples(db)
            assert len(rows) == 2
            assert all(row.player_games_before == 0 for row in rows)
    finally:
        engine.dispose()


def test_unparseable_or_timezone_naive_dates_are_excluded(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="A")
            b = Player(external_id="2", name="B")
            db.add_all([a, b])
            db.flush()
            bad = Match(external_id="101", match_date="01/02/2024", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            naive = Match(external_id="102", match_date="2024-02-01T19:00:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            good = Match(external_id="103", match_date="2024-03-01T19:00:00-07:00", format="EIGHT", session_name="S1", is_scored=True, is_finalized=True, is_bye=False)
            db.add_all([bad, naive, good])
            db.flush()
            _add_game(db, bad, a, b, "W")
            _add_game(db, naive, a, b, "W")
            _add_game(db, good, a, b, "L")
            db.commit()

            rows = build_backtest_examples(db)
            assert [row.match_external_id for row in rows] == ["103"]
            assert rows[0].direct_games_before == 0
    finally:
        engine.dispose()
