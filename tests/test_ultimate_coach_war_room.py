"""Unit tests for analytics.ultimate_coach_war_room (Captain's War Room data)."""

from __future__ import annotations

from analytics.ultimate_coach_matchup_evidence import build_pair_index
from analytics.ultimate_coach_war_room import (
    CATEGORY_LABELS,
    build_local_date,
    category,
    cell_text,
    default_matchup,
    explanation,
    filter_codes,
    freshness,
    meetings_index,
    scope_dates,
    sl_bucket_index,
    suggested_date,
    war_room_pair,
)


def _m(pid, name, sl=4, won=3, played=5):
    return {"id": pid, "external_id": str(1000 + pid), "name": name, "skill_level": sl,
            "matches_won": won, "matches_played": played}


def _pairs(*rows):
    return [{"player_id": p, "opponent_id": o, "format": "EIGHT", "wins": w, "games": g} for p, o, w, g in rows]


def _row(direct=None, shared=0, ours=(0, 0), theirs=(0, 0)):
    return {"direct": direct, "shared_count": shared, "ours": ours, "theirs": theirs}


def test_category_rule_uses_only_the_sign_of_the_record_and_whether_evidence_exists():
    assert category(_row(direct=(2, 3))) == "G"
    assert category(_row(direct=(1, 3))) == "R"
    assert category(_row(direct=(1, 2))) == "E"
    assert category(_row(direct=(1, 1))) == "G"  # one meeting is still "favorable" -- the sample size is shown
    assert category(_row(shared=3, ours=(4, 6), theirs=(1, 5))) == "I"
    assert category(_row()) == "X"
    assert set(CATEGORY_LABELS) == {"G", "R", "E", "I", "X"}


def test_cell_text_and_explanation_name_the_records_and_sample_sizes():
    assert cell_text(_row(direct=(2, 3))) == "2-1 (3)"
    assert cell_text(_row(shared=4, ours=(6, 9), theirs=(5, 9))) == "≈ 6-3 vs 5-4 (4 shared)"
    assert cell_text(_row()) == "No evidence"
    assert explanation(_row(direct=(2, 3), shared=4, ours=(6, 9), theirs=(5, 9))) == (
        "Direct: 2-1 in 3 meetings · Indirect: 4 shared opponents — ours 6-3 (9 games), theirs 5-4 (9 games)")
    assert explanation(_row()) == "No direct meetings · no shared opponents"


def _war_room():
    ours = [_m(1, "Ann", sl=5), _m(2, "Bea", sl=4), _m(3, "Cal", sl=None)]
    theirs = [_m(50, "Opal", sl=6, won=7, played=9), _m(51, "Pip", sl=3), _m(52, "Quin", sl=None)]
    index = build_pair_index(_pairs(
        (1, 50, 0, 3), (50, 1, 3, 3),          # Ann lost 0-3 to Opal
        (2, 50, 2, 3), (50, 2, 1, 3),          # Bea beat Opal 2-1
        (2, 70, 1, 1), (51, 70, 1, 2),         # Bea & Pip share opponent 70
        (3, 51, 1, 2), (51, 3, 1, 2),          # Cal even 1-1 with Pip
    ))
    evidence = [
        {"player_id": 50, "opponent_id": 1, "format": "EIGHT", "result": "W", "opponent_skill_level": 5,
         "match_date": "2026-09-01T19:00:00-06:00", "session_name": "Fall 2026", "own_skill_level": 6,
         "points_earned": 3},
        {"player_id": 50, "opponent_id": 2, "format": "EIGHT", "result": "L", "opponent_skill_level": 4,
         "match_date": "2026-09-08T19:00:00-06:00", "session_name": "Fall 2026", "own_skill_level": 6,
         "points_earned": 0},
        {"player_id": 1, "opponent_id": 50, "format": "EIGHT", "result": "L", "opponent_skill_level": 6,
         "match_date": "2026-09-01T19:00:00-06:00", "session_name": "Fall 2026", "own_skill_level": 5,
         "points_earned": 0},
    ]
    ids = {1, 2, 3, 50, 51, 52}
    return war_room_pair(ours, theirs, index, "EIGHT", sl_index=sl_bucket_index(evidence, ids),
                         meetings=meetings_index(evidence, ids, "America/Denver"), session_name="Fall 2026")


def test_matrix_is_our_roster_by_their_roster_in_roster_order_with_categories():
    wr = _war_room()
    assert [r["member"]["name"] for r in wr["matrix"]] == ["Ann", "Bea", "Cal"]
    assert [c["opponent"]["name"] for c in wr["cards"]] == ["Opal", "Pip", "Quin"]
    cats = [[cell["category"] for cell in row["cells"]] for row in wr["matrix"]]
    assert cats == [["R", "X", "X"], ["G", "I", "X"], ["X", "E", "X"]]
    assert wr["matrix"][1]["cells"][1]["cell"] == "≈ 1-0 vs 1-1 (1 shared)"


def test_best_sends_keep_ranking_order_and_drop_only_concerning_and_missing_evidence():
    wr = _war_room()
    opal, pip, quin = wr["best_sends"]
    assert [r["member"]["name"] for r in opal] == ["Bea"]          # Ann's 0-3 is concerning, Cal has nothing
    assert [r["member"]["name"] for r in pip] == ["Cal", "Bea"]    # even direct record before indirect-only
    assert quin == []


def test_concerning_pairings_and_threats_are_factual_and_unknown_is_not_weak():
    wr = _war_room()
    assert [c["text"] for c in wr["concerning"]] == [
        "Ann (APA record ID 1001) vs Opal (APA record ID 1050): 0-3 direct (3 meetings)"]
    opal, pip, quin = wr["cards"]
    assert opal["vs_ours"] == "4-2 in 6 meetings with 2 of our 3 players"
    assert opal["met_list"] == "vs Ann (APA record ID 1001): 3-0 · vs Bea (APA record ID 1002): 1-2"
    assert [t["opponent"]["name"] for t in wr["threats"]] == ["Opal"]
    assert wr["threats"][0]["threat_text"] == (
        "Opal (APA record ID 1050) · SL 6 · 4-2 vs our roster (6 meetings, 2 of our players)")
    assert quin["vs_ours"] == "No recorded meetings with our roster — unknown, not a sign of weakness"
    assert "No captured SL on this team's roster" in quin["missing"]


def test_scouting_card_shows_records_by_opponent_skill_level_without_judgement():
    opal = _war_room()["cards"][0]
    assert opal["team_record"] == "7-2 (this team, Fall 2026)"
    assert opal["by_sl"] == "vs SL4 0-1 · vs SL5 1-0"
    assert opal["winning_sl"] == "SL5 (1-0)" and opal["losing_sl"] == "SL4 (0-1)"
    assert opal["lifetime"] == "No career stats captured"


def test_meetings_list_every_direct_game_between_the_rosters_newest_first():
    wr = _war_room()
    assert [(g["date"], g["our"]["name"], g["opp"]["name"], g["result"]) for g in wr["meetings"]] == [
        ("Tue Sep 1, 2026", "Ann", "Opal", "L")]


def test_schedule_helpers_suggest_the_earliest_date_on_or_after_the_build_date():
    match_day = {
        "fixtures": [
            {"local_date": "2026-10-04", "format": "EIGHT", "format_raw": "8-Ball Open", "local_sort": "a", "is_scored": True,
             "status": "COMPLETED"},
            {"local_date": "2026-10-11", "format": "EIGHT", "format_raw": "8-Ball Open", "local_sort": "b", "is_scored": False,
             "status": "UNPLAYED"},
            {"local_date": "2026-10-05", "format": "NINE", "format_raw": "9-Ball Open", "local_sort": "c", "is_scored": False,
             "status": "UNPLAYED"},
        ],
        "schedule": {
            "A": [{"fixture_index": 0, "opponent": {"scope_key": "B"}}, {"fixture_index": 1, "opponent": {"scope_key": "B"}}],
            "C": [{"fixture_index": 2, "opponent": {"scope_key": "D"}}],
        },
    }
    assert filter_codes(match_day["fixtures"][0]) == ["89", "ALL", "F:8-Ball Open"]
    dates = scope_dates(match_day)
    assert dates[("A", "89")] == ["2026-10-04", "2026-10-11"]
    assert suggested_date(dates[("A", "89")], "2026-10-07") == "2026-10-11"
    assert suggested_date(dates[("A", "89")], "2026-12-01") is None
    default = default_matchup(match_day, ["A", "C"], "2026-10-07", {"A": "A team", "C": "C team"})
    assert (default["scope"], default["date"], default["opponent_scope"]) == ("A", "2026-10-11", "B")
    fresh = freshness(match_day, "2026-10-07")
    assert fresh["latest_result"] == "Sun Oct 4, 2026"
    assert fresh["unplayed_before_build"] == 1  # Oct 5 still UNPLAYED in the snapshot
    assert fresh["build_date"] == "Wed Oct 7, 2026"


def test_build_local_date_is_the_denver_calendar_day_of_the_build_stamp():
    assert build_local_date("2026-10-07 04:30 UTC", "America/Denver") == "2026-10-06"
    assert build_local_date("2026-10-07 18:00 UTC", "America/Denver") == "2026-10-07"
    assert build_local_date("", "America/Denver") is None


# ---- career record: never fabricate losses from missing wins (GPT audit, issue #84) ----

def _career(*rows):
    from analytics.ultimate_coach_war_room import _career_text
    return _career_text({"career_stats": [{"format": "EIGHT", "matches_won": w, "matches_played": g} for w, g in rows]},
                        "EIGHT")


def test_career_missing_wins_is_not_a_zero_win_record():
    assert _career((None, 10)) == "No complete career record captured (1 league scope with missing wins or games not counted)"


def test_career_missing_played_is_not_counted():
    assert _career((4, None)) == "No complete career record captured (1 league scope with missing wins or games not counted)"


def test_career_partial_scopes_count_only_complete_ones_and_say_so():
    assert _career((6, 8), (None, 10), (3, None)) == (
        "6-2 (league-scoped lifetime 8-Ball; 2 league scopes with missing wins or games not counted)")
    assert _career((6, 8), (11, 10)) == "6-2 (league-scoped lifetime 8-Ball; 1 league scope with missing wins or games not counted)"


def test_career_genuine_zero_wins_is_kept():
    assert _career((0, 10)) == "0-10 (league-scoped lifetime 8-Ball)"
    assert _career((0, 0)) == "No career games recorded"
    assert _career() == "No career stats captured"
