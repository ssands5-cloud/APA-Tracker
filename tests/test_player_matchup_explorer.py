"""Tests for analytics/player_matchup_explorer.py and its builder/renderer.

The load-bearing property is the separation between captured meetings and a
modeled comparison: a pair who never met must say so, must not gain a
meeting from sharing a match or a team, and must still be able to show a
clearly-labeled modeled number without that number implying play.
"""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from analytics.player_matchup_explorer import (
    MODELED_LABEL,
    NO_DIRECT_MEETINGS,
    build_document,
)
from database.models import Base, Match, Player, PlayerHeadToHead, PlayerTeamHistory
from scripts.build_player_matchup_explorer import (
    build,
    captured_pair_histories,
    selectable_players,
)
from ui.export_html_player_matchup_explorer import render

SESSION = "2026 Rehearsal Session"


def player(pid, name, team="T1", team_name="Team One", skill=5, external=None):
    return {
        "player_id": pid, "player_external_id": external or f"P{pid}",
        "player_name": name, "team_external_id": team, "team_name": team_name,
        "skill_level": skill,
    }


def game(result="W", own=5, opp=5, date="2026-01-15", week=1, match_id="M1", points=3.0):
    return {
        "match_id": match_id, "match_date": date, "week": week,
        "own_skill_level": own, "opponent_skill_level": opp,
        "result": result, "points_earned": points,
    }


class TestCapturedMeetings:
    def test_a_real_history_yields_exact_counts_and_record(self):
        doc = build_document(
            [player(1, "Ann"), player(2, "Uma", team="T2", team_name="Team Two")],
            {(1, 2): [game("W"), game("L"), game("W")]},
            session_name=SESSION,
        )
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert pair.meetings == 3
        assert pair.wins == 2
        assert pair.losses == 1
        assert len(pair.games) == 3
        assert pair.unavailable_reason is None

    def test_each_game_keeps_its_date_skills_and_outcome(self):
        doc = build_document(
            [player(1, "Ann"), player(2, "Uma")],
            {(1, 2): [game("W", own=5, opp=7, date="2026-03-15", week=3, match_id="M9")]},
            session_name=SESSION,
        )
        entry = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2).games[0]

        assert entry.match_date == "2026-03-15"
        assert entry.week == 3
        assert entry.match_id == "M9"
        assert entry.own_skill_level == 5
        assert entry.opponent_skill_level == 7
        assert entry.result == "W"

    def test_an_undecided_game_is_counted_separately_not_as_a_loss(self):
        doc = build_document(
            [player(1, "Ann"), player(2, "Uma")],
            {(1, 2): [game("W"), game(None)]},
            session_name=SESSION,
        )
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert (pair.wins, pair.losses, pair.undecided) == (1, 0, 1)


class TestNeverInferred:
    def test_a_pair_with_no_captured_history_says_so(self):
        doc = build_document([player(1, "Ann"), player(2, "Uma")], {}, session_name=SESSION)
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert pair.meetings == 0
        assert pair.games == ()
        assert pair.unavailable_reason == NO_DIRECT_MEETINGS
        assert pair.has_direct_history is False

    def test_two_players_on_the_same_team_are_selectable_and_have_no_meetings(self):
        """Two opponents on one other team can be compared, and sharing a
        team never manufactures a meeting between them."""
        doc = build_document(
            [
                player(1, "Uma", team="T2", team_name="Team Two"),
                player(2, "Vik", team="T2", team_name="Team Two"),
            ],
            {},
            session_name=SESSION,
        )
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert pair.unavailable_reason == NO_DIRECT_MEETINGS
        assert pair.meetings == 0

    def test_history_against_a_third_player_never_leaks_into_another_pair(self):
        doc = build_document(
            [player(1, "Ann"), player(2, "Uma"), player(3, "Vik")],
            {(1, 2): [game("W"), game("W")]},
            session_name=SESSION,
        )
        unrelated = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 3)

        assert unrelated.meetings == 0
        assert unrelated.unavailable_reason == NO_DIRECT_MEETINGS

    def test_a_player_is_never_paired_with_themselves(self):
        doc = build_document([player(1, "Ann"), player(2, "Uma")], {}, session_name=SESSION)

        assert all(p.player_id != p.opponent_id for p in doc.pairs)
        assert len(doc.pairs) == 2  # 2 players -> 2 ordered pairs


class TestModeledComparisonIsSeparate:
    def test_it_exists_even_with_no_captured_meetings(self):
        doc = build_document([player(1, "Ann", skill=6), player(2, "Uma", skill=4)], {},
                             session_name=SESSION)
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert pair.modeled_skill_only_probability is not None
        assert pair.unavailable_reason == NO_DIRECT_MEETINGS

    def test_it_is_null_when_a_skill_level_is_missing(self):
        doc = build_document([player(1, "Ann", skill=None), player(2, "Uma", skill=4)], {},
                             session_name=SESSION)
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        assert pair.modeled_skill_only_probability is None

    def test_it_does_not_change_the_captured_record(self):
        doc = build_document(
            [player(1, "Ann", skill=7), player(2, "Uma", skill=2)],
            {(1, 2): [game("L")]},
            session_name=SESSION,
        )
        pair = next(p for p in doc.pairs if p.player_id == 1 and p.opponent_id == 2)

        # Heavily favored by skill, but the one real captured game is a loss.
        assert pair.modeled_skill_only_probability > 0.5
        assert (pair.wins, pair.losses, pair.meetings) == (0, 1, 1)


class TestRender:
    def _doc(self):
        return build_document(
            [player(1, "Ann"), player(2, "Uma", team="T2", team_name="Team Two")],
            {(1, 2): [game("W")]},
            session_name=SESSION,
        )

    def test_both_players_are_selectable(self):
        html = render(self._doc())

        assert html.count("<option value=") >= 4  # two selects, two players each
        assert "Ann" in html and "Uma" in html

    def test_the_no_meetings_message_and_modeled_label_are_present(self):
        html = render(self._doc())

        assert NO_DIRECT_MEETINGS in html
        assert MODELED_LABEL in html

    def test_hostile_names_are_escaped(self):
        doc = build_document(
            [player(1, "<script>alert(1)</script>"), player(2, "Uma")],
            {}, session_name=SESSION,
        )
        html = render(doc)

        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_no_external_resources(self):
        html = render(self._doc())

        assert "http://" not in html
        assert "https://" not in html


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _add_player(db, external_id, name, team_id, team_name, skill):
    row = Player(external_id=external_id, name=name)
    db.add(row)
    db.flush()
    db.add(PlayerTeamHistory(
        player_id=row.id, team_external_id=team_id, team_name=team_name,
        session_name=SESSION, is_current=True, skill_level=skill, division_id="D1",
    ))
    db.flush()
    return row


class TestBuilderScope:
    def test_players_from_every_team_in_the_session_are_selectable(self, db):
        _add_player(db, "A1", "Ann", "T1", "Team One", 5)
        _add_player(db, "B1", "Uma", "T2", "Team Two", 5)
        _add_player(db, "C1", "Zoe", "T3", "Team Three", 4)

        players = selectable_players(db, SESSION)

        assert {p["player_name"] for p in players} == {"Ann", "Uma", "Zoe"}

    def test_another_session_is_excluded(self, db):
        row = _add_player(db, "A1", "Ann", "T1", "Team One", 5)
        other = Player(external_id="X1", name="Other Session")
        db.add(other)
        db.flush()
        db.add(PlayerTeamHistory(
            player_id=other.id, team_external_id="T9", team_name="Nine",
            session_name="Some Other Session", is_current=True, skill_level=5,
        ))
        db.flush()

        names = {p["player_name"] for p in selectable_players(db, SESSION)}

        assert names == {"Ann"}

    def test_captured_histories_come_only_from_real_rows(self, db):
        ann = _add_player(db, "A1", "Ann", "T1", "Team One", 5)
        uma = _add_player(db, "B1", "Uma", "T2", "Team Two", 5)
        zoe = _add_player(db, "C1", "Zoe", "T3", "Team Three", 4)
        db.add(Match(external_id="M1", session_name=SESSION, format="8-Ball Open", week=1))
        db.flush()
        match = db.query(Match).filter_by(external_id="M1").one()
        db.add(PlayerHeadToHead(
            player_id=ann.id, opponent_id=uma.id, match_id=match.id,
            own_skill_level=5, opponent_skill_level=5, result="W",
            points_earned=3.0, session_name=SESSION, format="8-Ball Open",
        ))
        db.flush()

        histories = captured_pair_histories(db, {ann.id, uma.id, zoe.id}, SESSION)

        assert (ann.id, uma.id) in histories
        assert (ann.id, zoe.id) not in histories
        assert (uma.id, zoe.id) not in histories

    def test_end_to_end_writes_a_real_page(self, db, tmp_path):
        _add_player(db, "A1", "Ann", "T1", "Team One", 5)
        _add_player(db, "B1", "Uma", "T2", "Team Two", 5)

        html_path = build(db, SESSION, tmp_path)

        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Ann" in html and "Uma" in html
        payload = json.loads(re.search(r'id="pme-data">(.*?)</script>', html, re.S).group(1))
        assert len(payload["players"]) == 2
        assert len(payload["pairs"]) == 2
