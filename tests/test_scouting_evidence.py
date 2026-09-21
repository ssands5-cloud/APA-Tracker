"""Tests for transparent shared-opponent scouting evidence."""

from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.scouting_evidence import build_scouting_evidence
from database.engine import create_db_engine
from database.models import Match, Player, PlayerHeadToHead


def _seed(db):
    paul = Player(external_id="1", name="Paul")
    target = Player(external_id="2", name="Target")
    shared = Player(external_id="3", name="Shared")
    other = Player(external_id="4", name="Other")
    db.add_all([paul, target, shared, other])
    db.flush()

    matches = [
        Match(external_id=str(100 + n), format="EIGHT", session_name="S", is_scored=True, is_finalized=True)
        for n in range(5)
    ]
    db.add_all(matches)
    db.flush()

    rows = [
        # Direct Paul vs Target: 1-0.
        PlayerHeadToHead(player_id=paul.id, opponent_id=target.id, match_id=matches[0].id, result="W", format="EIGHT", session_name="S", own_skill_level=4, opponent_skill_level=5),
        # Paul vs Shared: 1-1.
        PlayerHeadToHead(player_id=paul.id, opponent_id=shared.id, match_id=matches[1].id, result="W", format="EIGHT", session_name="S", own_skill_level=4, opponent_skill_level=4),
        PlayerHeadToHead(player_id=paul.id, opponent_id=shared.id, match_id=matches[2].id, result="L", format="EIGHT", session_name="S", own_skill_level=4, opponent_skill_level=4),
        # Target vs Shared: 0-1.
        PlayerHeadToHead(player_id=target.id, opponent_id=shared.id, match_id=matches[3].id, result="L", format="EIGHT", session_name="S", own_skill_level=5, opponent_skill_level=4),
        # Paul-only opponent must not appear in shared evidence.
        PlayerHeadToHead(player_id=paul.id, opponent_id=other.id, match_id=matches[4].id, result="W", format="EIGHT", session_name="S", own_skill_level=4, opponent_skill_level=3),
    ]
    db.add_all(rows)
    db.commit()
    return paul, target, shared, other


def test_shared_opponent_evidence_is_real_record_only(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            paul, target, shared, other = _seed(db)
            report = build_scouting_evidence(
                db, player_id=paul.id, comparison_player_id=target.id, format_name="EIGHT"
            )

            assert report.probability_status == "NOT_CALIBRATED"
            assert report.direct_record.games == 1
            assert report.direct_record.wins == 1
            assert report.shared_opponent_count == 1
            assert report.shared_opponents[0].opponent_id == shared.id
            assert report.shared_opponents[0].player_record.games == 2
            assert report.shared_opponents[0].player_record.win_rate == 0.5
            assert report.shared_opponents[0].comparison_record.games == 1
            assert report.shared_opponents[0].comparison_record.win_rate == 0.0
            assert all(item.opponent_id != other.id for item in report.shared_opponents)
    finally:
        engine.dispose()


def test_format_is_strictly_separated(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            paul, target, _, _ = _seed(db)
            report = build_scouting_evidence(
                db, player_id=paul.id, comparison_player_id=target.id, format_name="NINE"
            )
            assert report.direct_record.games == 0
            assert report.shared_opponent_count == 0
            assert report.player_shared_record.games == 0
    finally:
        engine.dispose()


def test_self_comparison_rejected(tmp_path):
    engine = create_db_engine({"database": {"path": str(tmp_path / "x.db")}})
    try:
        with Session(engine) as db:
            paul, _, _, _ = _seed(db)
            try:
                build_scouting_evidence(
                    db, player_id=paul.id, comparison_player_id=paul.id, format_name="EIGHT"
                )
            except ValueError as exc:
                assert "themself" in str(exc)
            else:
                raise AssertionError("self-comparison must be rejected")
    finally:
        engine.dispose()
