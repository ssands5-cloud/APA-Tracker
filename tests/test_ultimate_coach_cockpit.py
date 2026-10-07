"""Tests for the standalone Ultimate Coach Scout & Compare cockpit."""

from __future__ import annotations

from sqlalchemy.orm import Session

from analytics.ultimate_coach_payload import build_ultimate_coach_payload
from database.engine import create_db_engine
from database.models import Match, Player, PlayerHeadToHead, PlayerLeagueCareerStats, PlayerTeamHistory
from ui.ultimate_coach import render


def test_payload_preserves_real_profile_and_format_evidence(tmp_path):
    engine=create_db_engine({"database":{"path":str(tmp_path/"x.db")}})
    try:
        with Session(engine) as db:
            a=Player(external_id="1",name="Alpha",skill_level=4)
            b=Player(external_id="2",name="Bravo",skill_level=5)
            db.add_all([a,b]); db.flush()
            db.add(PlayerTeamHistory(player_id=a.id,team_external_id="10",team_name="Team A",division_id="99",session_name="Fall 2026",skill_level=4,is_current=True))
            db.add(PlayerLeagueCareerStats(player_id=a.id,league_id="12",league_slug="league",alias_external_id="100",format="EIGHT",matches_won=10,matches_played=20,break_and_runs=2))
            match=Match(external_id="500",home_team_id="10",away_team_id="20",match_date="2026-09-01T19:00:00-06:00",format="EIGHT",session_name="Fall 2026",is_scored=True,is_finalized=True)
            db.add(match); db.flush()
            db.add(PlayerHeadToHead(player_id=a.id,opponent_id=b.id,match_id=match.id,result="W",format="EIGHT",session_name="Fall 2026",own_skill_level=4,opponent_skill_level=5,points_earned=3))
            db.commit()

            payload=build_ultimate_coach_payload(db)
            assert payload["probability_status"]=="NOT_CALIBRATED"
            assert payload["counts"]["players"] == 2
            assert payload["counts"]["head_to_head_rows"] == 1
            assert payload["counts"]["all_games"] == 1
            assert payload["source_contract_schema"] == "ultimate-coach-data-contract-v1"
            alpha=next(p for p in payload["players"] if p["name"]=="Alpha")
            assert alpha["career_stats"][0]["matches_played"]==20
            assert alpha["team_history"][0]["session_name"]=="Fall 2026"
            assert alpha["team_history"][0]["format"]=="EIGHT"
            assert payload["evidence"][0]["format"]=="EIGHT"
    finally:
        engine.dispose()


def test_html_never_claims_uncalibrated_probability():
    payload={
        "schema":"ultimate-coach-cockpit-v1",
        "probability_status":"NOT_CALIBRATED",
        "players":[
            {"id":1,"external_id":"1","name":"Alpha","current_skill_level":4,"current_matches_won":None,"current_matches_played":None,"team_history":[],"career_stats":[]},
            {"id":2,"external_id":"2","name":"Bravo","current_skill_level":5,"current_matches_won":None,"current_matches_played":None,"team_history":[],"career_stats":[]},
        ],
        "evidence":[],
        "counts":{"players":2,"head_to_head_rows":0},
    }
    html=render(payload)
    assert "Probability status: NOT CALIBRATED" in html
    assert "No matchup probability is displayed until" in html
    assert "Player A" in html and "Player B" in html
    assert "Shared-opponent evidence" in html


def test_format_selectors_offer_real_non_eight_nine_evidence():
    payload={
        "schema":"ultimate-coach-cockpit-v1",
        "probability_status":"NOT_CALIBRATED",
        "players":[
            {"id":1,"external_id":"1","name":"Alpha","current_skill_level":4,"current_matches_won":None,"current_matches_played":None,"team_history":[],"career_stats":[]},
            {"id":2,"external_id":"2","name":"Bravo","current_skill_level":5,"current_matches_won":None,"current_matches_played":None,"team_history":[],"career_stats":[]},
        ],
        "evidence":[
            # Alpha and Bravo have no 8-Ball/9-Ball history together -- only
            # this one real, distinct APA format (see
            # scraper.graphql_scraper._VALID_FORMATS). It must stay
            # reachable from both Format selectors rather than silently
            # reading as "no recorded direct meeting" because the dropdown
            # only ever offered EIGHT/NINE.
            {"player_id":1,"opponent_id":2,"match_id":1,"match_external_id":"1","match_date":"2026-01-01","session_name":"S","format":"MASTERS ALT","result":"W","own_skill_level":4,"opponent_skill_level":5,"points_earned":3,"nine_ball_points":None},
            {"player_id":2,"opponent_id":1,"match_id":1,"match_external_id":"1","match_date":"2026-01-01","session_name":"S","format":"MASTERS ALT","result":"L","own_skill_level":5,"opponent_skill_level":4,"points_earned":None,"nine_ball_points":None},
        ],
        "counts":{"players":2,"head_to_head_rows":2},
    }
    html=render(payload)

    # Player + Team selectors use format codes. Match Day's own filter lists
    # raw recorded fixture labels instead (see analytics.ultimate_coach_match_day),
    # so it is not counted here.
    assert html.count('<option value="MASTERS ALT">Masters Alt</option>') == 2
    assert html.count('<option value="EIGHT">8-Ball</option>') == 2
    assert html.count('<option value="NINE">9-Ball</option>') == 2
