"""Tests for the canonical Ultimate Coach data contract."""

from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.ultimate_coach_data_contract import build_contract, normalize_format
from database.engine import create_db_engine
from database.models import Match, Player, PlayerHeadToHead, PlayerMatch


def _engine(tmp_path):
    return create_db_engine({"database": {"path": str(tmp_path / "x.db")}})


def _match(db):
    match = Match(
        external_id="500",
        match_date="2026-09-01T19:00:00-06:00",
        format="EIGHT",
        session_name="Fall 2026",
        week=1,
        is_scored=True,
        is_finalized=True,
    )
    db.add(match)
    db.flush()
    return match


def test_all_games_collapses_clean_mirror_to_one_game(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="Alpha")
            b = Player(external_id="2", name="Bravo")
            db.add_all([a, b]); db.flush()
            match = _match(db)
            db.add_all([
                PlayerMatch(player_id=a.id, match_id=match.id, team_id="TA", team_name="Team A", skill_level=4),
                PlayerMatch(player_id=b.id, match_id=match.id, team_id="TB", team_name="Team B", skill_level=5),
                PlayerHeadToHead(player_id=a.id, opponent_id=b.id, match_id=match.id, result="W", own_skill_level=4, opponent_skill_level=5, points_earned=3, format="EIGHT", session_name="Fall 2026"),
                PlayerHeadToHead(player_id=b.id, opponent_id=a.id, match_id=match.id, result="L", own_skill_level=5, opponent_skill_level=4, points_earned=0, format="EIGHT", session_name="Fall 2026"),
            ])
            db.commit()

            contract = build_contract(db)
            assert len(contract["tables"]["raw_h2h_evidence"]) == 2
            games = contract["tables"]["all_games"]
            assert len(games) == 1
            assert games[0]["winner_name"] == "Alpha"
            assert games[0]["participant_a_team_name"] == "Team A"
            assert games[0]["mirror_status"] == "VERIFIED_UNIQUE"
    finally:
        engine.dispose()


def test_repeated_same_pair_is_not_silently_collapsed(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="Alpha")
            b = Player(external_id="2", name="Bravo")
            db.add_all([a, b]); db.flush()
            match = _match(db)
            for _ in range(2):
                db.add(PlayerHeadToHead(player_id=a.id, opponent_id=b.id, match_id=match.id, result="W", own_skill_level=4, opponent_skill_level=5, format="EIGHT", session_name="Fall 2026"))
                db.add(PlayerHeadToHead(player_id=b.id, opponent_id=a.id, match_id=match.id, result="L", own_skill_level=5, opponent_skill_level=4, format="EIGHT", session_name="Fall 2026"))
            db.commit()

            contract = build_contract(db)
            games = contract["tables"]["all_games"]
            assert len(games) == 2
            assert {row["mirror_status"] for row in games} == {"VERIFIED_COUNT_ONLY"}
            assert any(
                issue["category"] == "GAME_MIRROR_STATUS"
                and "VERIFIED_COUNT_ONLY" in issue["detail"]
                for issue in contract["tables"]["coverage_issues"]
            )
    finally:
        engine.dispose()


def test_mirror_mismatch_stays_visible_and_is_flagged(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="Alpha")
            b = Player(external_id="2", name="Bravo")
            db.add_all([a, b]); db.flush()
            match = _match(db)
            db.add_all([
                PlayerHeadToHead(player_id=a.id, opponent_id=b.id, match_id=match.id, result="W", own_skill_level=4, opponent_skill_level=5, format="EIGHT", session_name="Fall 2026"),
                PlayerHeadToHead(player_id=b.id, opponent_id=a.id, match_id=match.id, result="W", own_skill_level=5, opponent_skill_level=4, format="EIGHT", session_name="Fall 2026"),
            ])
            db.commit()

            contract = build_contract(db)
            games = contract["tables"]["all_games"]
            assert len(games) == 1
            assert games[0]["mirror_status"] == "MIRROR_MISMATCH"
            assert any("MIRROR_MISMATCH" in row["detail"] for row in contract["tables"]["coverage_issues"])
    finally:
        engine.dispose()


def test_null_source_values_remain_null_not_zero(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="Alpha")
            b = Player(external_id="2", name="Bravo")
            db.add_all([a, b]); db.flush()
            match = _match(db)
            db.add_all([
                PlayerHeadToHead(player_id=a.id, opponent_id=b.id, match_id=match.id, result="W", own_skill_level=None, opponent_skill_level=None, points_earned=None, format="EIGHT", session_name="Fall 2026"),
                PlayerHeadToHead(player_id=b.id, opponent_id=a.id, match_id=match.id, result="L", own_skill_level=None, opponent_skill_level=None, points_earned=None, format="EIGHT", session_name="Fall 2026"),
            ])
            db.commit()

            row = build_contract(db)["tables"]["all_games"][0]
            assert row["participant_a_skill_level"] is None
            assert row["participant_a_points_earned"] is None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("8-BALL OPEN", "EIGHT"),
        ("8-Ball Open Tournament", "EIGHT"),
        ("8-BALL DOUBLES", "EIGHT"),
        ("8-BALL LADIES ALT", "EIGHT"),
        ("8 BALL OPEN", "EIGHT"),
        ("9-BALL OPEN", "NINE"),
        ("9-Ball Open Tournament", "NINE"),
        ("9 BALL OPEN", "NINE"),
        ("MASTERS", "MASTERS"),
    ],
)
def test_normalize_format_recognizes_real_apa_labels_without_reclassifying_other_formats(
    source, expected
):
    assert normalize_format(source) == expected


def test_real_apa_open_format_reaches_all_games_as_eight(tmp_path):
    engine = _engine(tmp_path)
    try:
        with Session(engine) as db:
            a = Player(external_id="1", name="Alpha")
            b = Player(external_id="2", name="Bravo")
            db.add_all([a, b])
            db.flush()
            match = Match(
                external_id="real-format-500",
                match_date="2026-09-01T19:00:00-06:00",
                format="8-BALL OPEN",
                session_name="Fall 2026",
                week=1,
                is_scored=True,
                is_finalized=True,
            )
            db.add(match)
            db.flush()
            db.add_all(
                [
                    PlayerMatch(
                        player_id=a.id,
                        match_id=match.id,
                        team_id="TA",
                        team_name="Team A",
                        skill_level=4,
                    ),
                    PlayerMatch(
                        player_id=b.id,
                        match_id=match.id,
                        team_id="TB",
                        team_name="Team B",
                        skill_level=5,
                    ),
                    PlayerHeadToHead(
                        player_id=a.id,
                        opponent_id=b.id,
                        match_id=match.id,
                        result="W",
                        own_skill_level=4,
                        opponent_skill_level=5,
                        points_earned=3,
                        format="8-BALL OPEN",
                        session_name="Fall 2026",
                    ),
                    PlayerHeadToHead(
                        player_id=b.id,
                        opponent_id=a.id,
                        match_id=match.id,
                        result="L",
                        own_skill_level=5,
                        opponent_skill_level=4,
                        points_earned=0,
                        format="8-BALL OPEN",
                        session_name="Fall 2026",
                    ),
                ]
            )
            db.commit()

            contract = build_contract(db)

            assert {row["format"] for row in contract["tables"]["raw_h2h_evidence"]} == {
                "EIGHT"
            }
            assert [row["format"] for row in contract["tables"]["all_games"]] == [
                "EIGHT"
            ]
    finally:
        engine.dispose()
