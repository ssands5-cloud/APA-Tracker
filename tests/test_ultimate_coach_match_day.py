"""Unit tests for the pure Match Day transforms (analytics.ultimate_coach_match_day)."""

from __future__ import annotations

from datetime import date, timedelta

from analytics.ultimate_coach_match_day import (
    build_fixture_rows,
    fixture_opponent,
    fixtures_for_team_on_date,
    load_viewer_external_id_from_config,
    load_viewer_external_id_from_file,
    match_local_date,
    parse_match_date,
    viewer_current_teams,
    viewer_player,
)


def test_viewer_external_id_missing_or_placeholder_is_none():
    assert load_viewer_external_id_from_config(None) is None
    assert load_viewer_external_id_from_config({}) is None
    assert load_viewer_external_id_from_config({"ultimate_coach": {}}) is None
    assert load_viewer_external_id_from_config({"ultimate_coach": {"viewer_member_external_id": "CHANGE_ME"}}) is None
    assert load_viewer_external_id_from_config({"ultimate_coach": {"viewer_member_external_id": "  "}}) is None


def test_viewer_external_id_real_value_is_returned_as_string():
    config = {"ultimate_coach": {"viewer_member_external_id": 1001}}
    assert load_viewer_external_id_from_config(config) == "1001"


def test_viewer_external_id_from_file_missing_file_is_none(tmp_path):
    assert load_viewer_external_id_from_file(tmp_path / "no_such_file.yaml") is None


def test_viewer_external_id_from_file_reads_real_config(tmp_path):
    config_path = tmp_path / "apa_config.yaml"
    config_path.write_text(
        "ultimate_coach:\n  viewer_member_external_id: \"1234567\"\n", encoding="utf-8"
    )
    assert load_viewer_external_id_from_file(config_path) == "1234567"


def test_viewer_external_id_from_file_placeholder_is_none(tmp_path):
    config_path = tmp_path / "apa_config.yaml"
    config_path.write_text(
        "ultimate_coach:\n  viewer_member_external_id: \"CHANGE_ME\"\n", encoding="utf-8"
    )
    assert load_viewer_external_id_from_file(config_path) is None


def test_viewer_external_id_from_file_malformed_yaml_is_advisory_not_fatal(tmp_path):
    config_path = tmp_path / "apa_config.yaml"
    config_path.write_text("not: valid: yaml: [", encoding="utf-8")
    assert load_viewer_external_id_from_file(config_path) is None


def test_parse_match_date_keeps_explicit_offset():
    parsed = parse_match_date("2026-08-09T11:00:00-06:00")
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(hours=-6)
    assert parsed.date() == date(2026, 8, 9)


def test_parse_match_date_keeps_utc_z_suffix_as_utc_not_guessed_zone():
    parsed = parse_match_date("2026-08-29T15:00:00Z")
    assert parsed is not None
    assert parsed.utcoffset() == timedelta(0)
    assert parsed.tzinfo is not None
    assert parsed.date() == date(2026, 8, 29)


def test_parse_match_date_never_raises_on_garbage():
    assert parse_match_date(None) is None
    assert parse_match_date("") is None
    assert parse_match_date("not a date") is None
    assert parse_match_date("2026-08-09") is None  # no offset -- not one of the two real shapes


def test_match_local_date_near_midnight_does_not_cross_days_from_its_own_offset():
    # 23:30 at UTC-06:00 is 05:30Z the *next* UTC day -- the local date must
    # stay the 9th (the offset actually recorded), never silently read off
    # a UTC-truncated day.
    assert match_local_date("2026-08-09T23:30:00-06:00") == date(2026, 8, 9)


def _fixture_row(**overrides):
    row = {
        "match_id": 1, "match_external_id": "1", "match_date": "2026-10-11T11:00:00-06:00",
        "format": "EIGHT", "session_name": "Fall 2026", "week": 7, "status": "UNPLAYED",
        "location": None, "home_team_id": "T1", "home_team_name": "Sharks",
        "away_team_id": "T2", "away_team_name": "Falcons", "home_score": None,
        "away_score": None, "is_bye": False, "is_scored": False, "is_finalized": False,
    }
    row.update(overrides)
    return row


def test_build_fixture_rows_adds_local_date_and_keeps_raw_string():
    fixtures = build_fixture_rows([_fixture_row()])
    assert fixtures[0]["local_date"] == "2026-10-11"
    assert fixtures[0]["match_date"] == "2026-10-11T11:00:00-06:00"
    assert fixtures[0]["date_unparsed"] is False


def test_build_fixture_rows_discloses_unparseable_date_rather_than_dropping_it():
    fixtures = build_fixture_rows([_fixture_row(match_date="garbage")])
    assert fixtures[0]["local_date"] is None
    assert fixtures[0]["date_unparsed"] is True


def test_build_fixture_rows_missing_date_is_not_flagged_as_unparsed():
    # A genuinely absent date is "no data", not a parse failure -- the two
    # must stay distinguishable so "disclose unparseable dates" doesn't
    # also fire for every ordinary missing-date row.
    fixtures = build_fixture_rows([_fixture_row(match_date=None)])
    assert fixtures[0]["local_date"] is None
    assert fixtures[0]["date_unparsed"] is False


def _player(pid, external_id, name, team_history):
    return {
        "id": pid, "external_id": external_id, "name": name,
        "current_skill_level": 4, "current_matches_won": None, "current_matches_played": None,
        "team_history": team_history, "career_stats": [],
    }


def _hist(team_external_id, division_id, session_name, *, is_current=True, fmt="EIGHT"):
    return {
        "team_external_id": team_external_id, "team_name": f"Team {team_external_id}",
        "division_id": division_id, "session_name": session_name, "format": fmt,
        "is_current": is_current, "skill_level": 4, "matches_won": 1, "matches_played": 2,
    }


def test_viewer_player_is_identity_backed_never_name_matched():
    players = [
        _player(1, "9001", "Paul Sands", [_hist("T1", "d1", "Fall 2026")]),
        _player(2, "9002", "Paul Sands", [_hist("T2", "d2", "Fall 2026")]),  # duplicate display name
    ]
    found = viewer_player(players, "9002")
    assert found is not None
    assert found["id"] == 2  # resolved by external_id, not by matching the shared name


def test_viewer_player_none_when_unconfigured_or_unresolved():
    players = [_player(1, "9001", "Paul Sands", [])]
    assert viewer_player(players, None) is None
    assert viewer_player(players, "9999-no-such-member") is None


def test_viewer_current_teams_excludes_historical_and_other_players():
    players = [
        _player(1, "9001", "Paul Sands", [
            _hist("T1", "d1", "Fall 2026", is_current=True),
            _hist("T0", "d0", "Spring 2020", is_current=False),
        ]),
        _player(2, "9002", "Someone Else", [_hist("T2", "d2", "Fall 2026", is_current=True)]),
    ]
    teams = viewer_current_teams(players, "9001")
    assert [t["team_external_id"] for t in teams] == ["T1"]


def test_viewer_current_teams_empty_when_unconfigured():
    players = [_player(1, "9001", "Paul Sands", [_hist("T1", "d1", "Fall 2026")])]
    assert viewer_current_teams(players, None) == []


def test_fixtures_for_team_on_date_scopes_by_session_not_bare_id():
    team = _hist("T1", "d1", "Fall 2026")
    fixtures = build_fixture_rows([
        _fixture_row(match_id=1, home_team_id="T1", session_name="Fall 2026", match_date="2026-10-11T11:00:00-06:00"),
        # Same external id, but a DIFFERENT session -- must not be pulled in.
        _fixture_row(match_id=2, home_team_id="T1", session_name="Spring 2020", match_date="2026-10-11T11:00:00-06:00"),
        # Right session, wrong date.
        _fixture_row(match_id=3, home_team_id="T1", session_name="Fall 2026", match_date="2026-10-18T11:00:00-06:00"),
    ])
    found = fixtures_for_team_on_date(fixtures, team, "2026-10-11")
    assert [f["match_id"] for f in found] == [1]


def test_fixtures_for_team_on_date_returns_all_without_picking_one():
    team = _hist("T1", "d1", "Fall 2026")
    fixtures = build_fixture_rows([
        _fixture_row(match_id=1, home_team_id="T1", away_team_id="T2", format="EIGHT"),
        _fixture_row(match_id=2, home_team_id="T1", away_team_id="T3", format="NINE", match_date="2026-10-11T19:00:00-06:00"),
    ])
    found = fixtures_for_team_on_date(fixtures, team, "2026-10-11")
    assert len(found) == 2
    # Sorted by kickoff time -- the 11:00 match before the 19:00 one.
    assert found[0]["match_id"] == 1


def test_fixture_opponent_identifies_the_other_side():
    fixture = _fixture_row(home_team_id="T1", home_team_name="Sharks", away_team_id="T2", away_team_name="Falcons")
    assert fixture_opponent(fixture, "T1") == {"team_external_id": "T2", "team_name": "Falcons", "side": "away"}
    assert fixture_opponent(fixture, "T2") == {"team_external_id": "T1", "team_name": "Sharks", "side": "home"}


def test_fixture_opponent_none_for_a_bye_never_fabricated():
    fixture = _fixture_row(is_bye=True, away_team_id="", away_team_name="")
    assert fixture_opponent(fixture, "T1") is None
