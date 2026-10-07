"""Unit tests for the pure Match Day transforms (analytics.ultimate_coach_match_day)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from analytics.ultimate_coach_match_day import (
    DEFAULT_MATCH_DAY_TIMEZONE,
    FORMAT_FILTER_ALL,
    FORMAT_FILTER_EIGHT_NINE,
    build_fixture_rows,
    build_match_day_section,
    excel_date_serial,
    fixture_matches_format_filter,
    load_match_day_settings,
    localize_match_date,
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


def test_match_local_date_near_midnight_is_never_read_off_a_utc_truncated_day():
    # 23:30 at UTC-06:00 is 05:30Z the *next* UTC day -- in the Denver
    # display timezone (MDT, also -06:00 in August) it stays the 9th.
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


# ---- display timezone (GPT finding: source UTC day is not the league day) ----

def test_real_utc_evening_match_lands_on_the_previous_denver_day():
    # Match 51545390 (Pool Cats vs Margin of Error, Summer 2026) is stored as
    # 2026-08-30T01:00:00Z -- Saturday Aug 29 at 7:00 PM in Denver.
    local = localize_match_date("2026-08-30T01:00:00Z")
    assert DEFAULT_MATCH_DAY_TIMEZONE == "America/Denver"
    assert local["local_date"] == "2026-08-29"
    assert local["local_weekday"] == "Saturday"
    assert local["local_time"] == "7:00 PM"
    assert local["local_tz_abbrev"] == "MDT"
    assert local["local_utc_offset"] == "-06:00"
    assert local["local_display"] == "Sat Aug 29, 2026 · 7:00 PM MDT"
    assert match_local_date("2026-08-30T01:00:00Z") == date(2026, 8, 29)


def test_winter_and_summer_offsets_use_mst_and_mdt():
    winter = localize_match_date("2027-01-10T02:30:00Z")  # 7:30 PM MST on Jan 9
    assert (winter["local_date"], winter["local_time"], winter["local_tz_abbrev"], winter["local_utc_offset"]) == (
        "2027-01-09", "7:30 PM", "MST", "-07:00")
    # A source row already carrying -07:00 in winter is the same wall clock.
    assert localize_match_date("2027-01-09T19:30:00-07:00")["local_display"] == winter["local_display"]
    summer = localize_match_date("2026-07-10T01:30:00Z")  # 7:30 PM MDT on Jul 9
    assert (summer["local_date"], summer["local_tz_abbrev"]) == ("2026-07-09", "MDT")


def test_offset_rows_recorded_in_another_zone_are_converted_not_trusted_as_local():
    # A real -08:00 source row (3 exist in Fall 2026) at 23:30 is 00:30 MST
    # the next day in Denver.
    local = localize_match_date("2026-11-13T23:30:00-08:00")
    assert (local["local_date"], local["local_time"]) == ("2026-11-14", "12:30 AM")


def test_dst_change_day_is_handled_by_the_timezone_database():
    # US DST ended 2026-11-01 at 2:00 AM MDT. 08:30Z is 1:30 AM MST that day.
    assert localize_match_date("2026-11-01T08:30:00Z")["local_display"] == "Sun Nov 1, 2026 · 1:30 AM MST"


def test_missing_and_unparseable_dates_are_distinguished_and_never_guessed():
    assert localize_match_date(None)["date_status"] == "missing"
    assert localize_match_date("  ")["date_status"] == "missing"
    bad = localize_match_date("2026-13-45T99:00:00Z")
    assert bad["date_status"] == "unparseable"
    assert bad["local_date"] is None and bad["local_display"] is None
    assert localize_match_date("2026-08-09")["date_status"] == "unparseable"  # naive: no instant


def test_another_display_timezone_can_be_chosen_explicitly():
    assert localize_match_date("2026-08-30T01:00:00Z", "UTC")["local_date"] == "2026-08-30"
    assert localize_match_date("2026-08-30T01:00:00Z", "America/New_York")["local_time"] == "9:00 PM"


def test_excel_date_serial_matches_excel_1900_system():
    assert excel_date_serial("2026-08-29") == 46263
    assert excel_date_serial(None) is None


# ---- settings shared by every build entrypoint ----

def test_settings_default_to_denver_and_no_viewer(tmp_path):
    settings = load_match_day_settings(tmp_path / "apa_config.yaml")
    assert settings.timezone == "America/Denver"
    assert settings.viewer_member_external_id is None
    assert settings.viewer_source == "not configured"


def test_local_override_supplies_viewer_and_card_without_touching_the_shared_config(tmp_path):
    (tmp_path / "apa_config.yaml").write_text(
        'ultimate_coach:\n  viewer_member_external_id: "CHANGE_ME"\n  viewer_card_number: "CHANGE_ME"\n'
        '  match_day_timezone: "America/Denver"\n', encoding="utf-8")
    (tmp_path / "apa_config.local.yaml").write_text(
        'ultimate_coach:\n  viewer_member_external_id: "3349374"\n  viewer_card_number: "80202016"\n', encoding="utf-8")
    settings = load_match_day_settings(tmp_path / "apa_config.yaml")
    assert settings.viewer_member_external_id == "3349374"
    assert settings.viewer_card_number == "80202016"
    assert settings.viewer_source == "apa_config.local.yaml"
    assert settings.timezone == "America/Denver"


def test_unknown_display_timezone_fails_the_build_instead_of_silently_defaulting(tmp_path):
    (tmp_path / "apa_config.yaml").write_text('ultimate_coach:\n  match_day_timezone: "Mars/Olympus"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Mars/Olympus"):
        load_match_day_settings(tmp_path / "apa_config.yaml")


# ---- the shared Match Day section ----

def test_section_embeds_only_fixtures_reachable_from_a_current_scope_and_counts_the_rest():
    players = [_player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")])]
    section = build_match_day_section([
        _fixture_row(match_id=1, home_team_id="T1", away_team_id="T2", session_name="Fall 2026"),
        _fixture_row(match_id=2, home_team_id="T1", away_team_id="T2", session_name="Summer 2026"),  # past session
        _fixture_row(match_id=3, home_team_id="X1", away_team_id="X2", session_name="Fall 2026"),
    ], players)
    assert [f["match_id"] for f in section["fixtures"]] == [1]
    assert section["coverage"] == {
        "stored_fixture_count": 3, "embedded_fixture_count": 1, "excluded_fixture_count": 2,
        "current_sessions": ["Fall 2026"], "current_scope_count": 1,
        "date_status_counts": {"ok": 1}, "location_missing_count": 1, "bye_count": 0,
    }
    side = section["schedule"]["T1|d1|Fall 2026"][0]
    assert side["side"] == "home"
    assert side["opponent"]["status"] == "no_current_roster"
    assert side["opponent"]["team_name"] == "Falcons"


def test_section_resolves_opponent_by_exact_id_and_session():
    players = [
        _player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")]),
        _player(2, "9002", "Opp", [_hist("T2", "d2", "Fall 2026"), _hist("T2", "d9", "Spring 2020", is_current=False)]),
    ]
    section = build_match_day_section([_fixture_row(home_team_id="T1", away_team_id="T2", session_name="Fall 2026")], players)
    opponent = section["schedule"]["T1|d1|Fall 2026"][0]["opponent"]
    assert opponent["status"] == "resolved"
    assert opponent["scope_key"] == "T2|d2|Fall 2026"
    # The opponent's own perspective is listed too, mirrored.
    assert section["schedule"]["T2|d2|Fall 2026"][0]["side"] == "away"


def test_section_discloses_ambiguous_opponent_scopes_instead_of_taking_first_or_last():
    players = [
        _player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")]),
        _player(2, "9002", "Opp A", [_hist("T2", "dA", "Fall 2026")]),
        _player(3, "9003", "Opp B", [_hist("T2", "dB", "Fall 2026")]),
    ]
    section = build_match_day_section([_fixture_row(home_team_id="T1", away_team_id="T2", session_name="Fall 2026")], players)
    opponent = section["schedule"]["T1|d1|Fall 2026"][0]["opponent"]
    assert opponent["status"] == "ambiguous"
    assert opponent["scope_key"] is None
    assert opponent["candidate_scope_keys"] == ["T2|dA|Fall 2026", "T2|dB|Fall 2026"]
    # And from T2's side, its own scope is flagged as ambiguous.
    assert all(s["own_scope_ambiguous"] for key in ("T2|dA|Fall 2026", "T2|dB|Fall 2026") for s in section["schedule"][key])


def test_section_bye_has_no_opponent_even_with_placeholder_names():
    players = [_player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")])]
    section = build_match_day_section([_fixture_row(home_team_id="T1", away_team_id="13082714", away_team_name="BYE",
                                                    session_name="Fall 2026", is_bye=True)], players)
    opponent = section["schedule"]["T1|d1|Fall 2026"][0]["opponent"]
    assert opponent == {"status": "bye", "scope_key": None, "candidate_scope_keys": [],
                        "team_external_id": None, "team_name": None}
    assert section["coverage"]["bye_count"] == 1


def test_section_missing_opponent_name_is_none_not_blank_or_zero():
    players = [_player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")])]
    section = build_match_day_section([_fixture_row(home_team_id="T1", away_team_id="T2", away_team_name="",
                                                    session_name="Fall 2026")], players)
    assert section["schedule"]["T1|d1|Fall 2026"][0]["opponent"]["team_name"] is None


def test_section_sorts_sides_by_display_time_with_undated_rows_last():
    players = [_player(1, "9001", "Viewer", [_hist("T1", "d1", "Fall 2026")])]
    section = build_match_day_section([
        _fixture_row(match_id=1, match_external_id="1", home_team_id="T1", session_name="Fall 2026", match_date=None),
        _fixture_row(match_id=2, match_external_id="2", home_team_id="T1", session_name="Fall 2026",
                     match_date="2026-10-12T02:00:00Z"),  # 8:00 PM Oct 11 Denver
        _fixture_row(match_id=3, match_external_id="3", home_team_id="T1", session_name="Fall 2026",
                     match_date="2026-10-11T11:00:00-06:00"),
    ], players)
    order = [section["fixtures"][s["fixture_index"]]["match_id"] for s in section["schedule"]["T1|d1|Fall 2026"]]
    assert order == [3, 2, 1]
    assert section["coverage"]["date_status_counts"] == {"missing": 1, "ok": 2}


def test_format_filter_default_keeps_every_eight_and_nine_variant_and_raw_labels_stay_selectable():
    doubles = build_fixture_rows([_fixture_row(format="EIGHT", format_raw="8-Ball Doubles")])[0]
    masters = build_fixture_rows([_fixture_row(format="MASTERS", format_raw="Masters")])[0]
    assert fixture_matches_format_filter(doubles, FORMAT_FILTER_EIGHT_NINE)
    assert not fixture_matches_format_filter(masters, FORMAT_FILTER_EIGHT_NINE)
    assert fixture_matches_format_filter(masters, FORMAT_FILTER_ALL)
    assert fixture_matches_format_filter(masters, "Masters")
    assert not fixture_matches_format_filter(doubles, "8-Ball Open")


def test_legacy_bare_format_codes_display_readably_but_keep_the_recorded_value():
    row = build_fixture_rows([_fixture_row(format="EIGHT", format_raw="EIGHT")])[0]
    assert row["format_raw"] == "EIGHT"
    assert row["format_display"] == "8-Ball (recorded as EIGHT)"
    assert build_fixture_rows([_fixture_row(format_raw="8-Ball Open")])[0]["format_display"] == "8-Ball Open"
