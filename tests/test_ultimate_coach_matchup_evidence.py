"""Unit tests for analytics.ultimate_coach_matchup_evidence (Match Night
team comparison + evidence ranking shared by the Excel companion and, via a
browser cross-check, the HTML cockpit)."""

from __future__ import annotations

from analytics.ultimate_coach_matchup_evidence import (
    build_pair_index,
    display_name,
    fixture_scope_pairs,
    matchup_evidence,
    member_order_key,
    player_ref,
    rank_vs_opponent,
    team_comparison,
)


def _m(pid, name, sl=4, ext=None):
    return {"id": pid, "external_id": ext if ext is not None else str(1000 + pid), "name": name, "skill_level": sl}


def _pairs(*rows):
    """(player, opponent, wins, games) -> Player vs Player pair rows for EIGHT."""
    return [{"player_id": p, "opponent_id": o, "format": "EIGHT", "wins": w, "games": g} for p, o, w, g in rows]


OPP = _m(50, "Opal Opp", sl=5)


def test_player_ref_names_alongside_record_id():
    assert player_ref(_m(1, "Ann Archer", ext="3349374")) == "Ann Archer"
    assert player_ref({"id": 2, "name": "No Id", "external_id": None}) == "No Id"


def test_display_name_omits_the_record_id_and_tells_duplicate_names_apart_without_it():
    """NAME-DISPLAY-01: Next Send and similar captain-facing surfaces (outside Players) never
    show the raw APA record ID, but two players sharing a name still need telling apart --
    a differing captured skill level does it; if even that ties, a readable position does,
    never the record ID itself."""
    roster = [_m(1, "Ann Archer", sl=5), _m(2, "Bea Baker", sl=4)]
    assert display_name(roster[0], roster) == "Ann Archer"          # no duplicate: plain name
    dup_roster = [_m(1, "Jordan Lee", sl=5), _m(2, "Jordan Lee", sl=7), _m(3, "Bea Baker", sl=4)]
    assert display_name(dup_roster[0], dup_roster) == "Jordan Lee (SL 5)"
    assert display_name(dup_roster[1], dup_roster) == "Jordan Lee (SL 7)"
    # Same name AND same skill level: falls back to a readable position, ordered the same way
    # the roster display order already is (member_order_key) -- lower external_id first here.
    tied_roster = [_m(1, "Jordan Lee", sl=5, ext="1001"), _m(2, "Jordan Lee", sl=5, ext="1002")]
    first, second = display_name(tied_roster[0], tied_roster), display_name(tied_roster[1], tied_roster)
    assert (first, second) == ("Jordan Lee (1 of 2 by this name)", "Jordan Lee (2 of 2 by this name)")
    assert "APA record ID" not in first and "APA record ID" not in second


def test_direct_ranks_before_shared_before_none_and_records_are_shown_with_samples():
    ours = [_m(1, "Ann"), _m(2, "Bea"), _m(3, "Cal")]
    index = build_pair_index(_pairs(
        (1, 50, 1, 3),          # Ann: direct 1-2 against Opal
        (2, 60, 4, 5), (50, 60, 1, 2),   # Bea and Opal both played 60
        (2, 61, 0, 1), (50, 61, 2, 2),   # ...and 61
    ))
    block = rank_vs_opponent(ours, OPP, index, "EIGHT")
    rows = block["rows"]
    assert [r["player"] for r in rows] == ["Ann", "Bea", "Cal"]
    assert [r["rank"] for r in rows] == ["1", "≈", "—"]  # indirect evidence is shown, never given a rank number
    assert rows[0]["direct_text"] == "1-2 (3 meetings)" and rows[0]["basis"] == "Direct record"
    assert rows[1]["direct_text"] == "No verified direct meetings in this snapshot"
    assert rows[1]["shared_text"] == "2 shared opponents · ours 4-2 (6 games) · theirs 3-1 (4 games)"
    assert rows[1]["basis"].startswith("Shared-opponent results only (no verified direct meetings in this snapshot)")
    assert rows[2]["shared_text"] == "No shared opponents"
    assert rows[2]["basis"] == "No verified direct or shared-opponent evidence in this snapshot"
    assert block["opponent_sample"] == "4 recorded games in 8-Ball"  # Opal: 2 vs player 60 + 2 vs player 61
    assert block["note"] == "2 of 3 of our players have direct or shared-opponent evidence against this opponent."


def test_within_direct_better_record_first_then_more_meetings():
    ours = [_m(1, "Ann"), _m(2, "Bea"), _m(3, "Cal")]
    index = build_pair_index(_pairs((1, 50, 1, 2), (2, 50, 2, 4), (3, 50, 2, 2)))
    rows = rank_vs_opponent(ours, OPP, index, "EIGHT")["rows"]
    # Cal 2-0 first; Ann 1-1 and Bea 2-2 share the same rate -> more meetings (Bea) first.
    assert [(r["player"].split(" (")[0], r["rank"]) for r in rows] == [("Cal", "1"), ("Bea", "2"), ("Ann", "3")]


def test_identical_evidence_is_a_tie_with_competition_ranking_and_an_explanation():
    ours = [_m(1, "Ann"), _m(2, "Bea"), _m(3, "Cal"), _m(4, "Dee")]
    index = build_pair_index(_pairs((1, 50, 2, 3), (2, 50, 1, 1), (3, 50, 1, 1), (4, 50, 0, 1)))
    rows = rank_vs_opponent(ours, OPP, index, "EIGHT")["rows"]
    assert [r["rank"] for r in rows] == ["1=", "1=", "3", "4"]
    assert [r["player"].split(" (")[0] for r in rows] == ["Bea", "Cal", "Ann", "Dee"]
    assert rows[0]["basis"] == ("Direct record · Tied with Cal — same evidence; "
                                "the ranking can't separate them")
    assert rows[1]["basis"].endswith("Tied with Bea — same evidence; the ranking can't separate them")
    assert "Tied" not in rows[2]["basis"]


def test_players_without_evidence_are_listed_but_never_ranked_or_tied():
    ours = [_m(1, "Ann"), _m(2, "Bea")]
    block = rank_vs_opponent(ours, OPP, build_pair_index([]), "EIGHT")
    assert [r["rank"] for r in block["rows"]] == ["—", "—"]
    assert all("Tied" not in r["basis"] for r in block["rows"])
    assert block["note"] == "No recorded 8-Ball games for this opponent in the verified evidence — nothing to rank on."
    assert block["opponent_sample"] == "0 recorded games in 8-Ball"


def test_formats_never_mix():
    ours = [_m(1, "Ann")]
    pairs = [{"player_id": 1, "opponent_id": 50, "format": "NINE", "wins": 3, "games": 3}]
    rows = rank_vs_opponent(ours, OPP, build_pair_index(pairs), "EIGHT")["rows"]
    assert rows[0]["rank"] == "—" and rows[0]["direct_text"] == "No verified direct meetings in this snapshot"


def test_team_comparison_counts_facts_and_discloses_missing_skill_levels():
    ours = [_m(1, "Ann", sl=4), _m(2, "Bea", sl=None)]
    theirs = [_m(50, "Opal", sl=5), _m(51, "Pip", sl=3)]
    index = build_pair_index(_pairs(
        (1, 50, 2, 3), (50, 1, 1, 3),              # Ann vs Opal: 3 games, Ann 2-1
        (2, 70, 1, 1), (51, 70, 0, 1),             # Bea and Pip share opponent 70
    ))
    c = team_comparison(ours, theirs, index, "EIGHT")
    assert c["format"] == "8-Ball"
    assert c["ours"] == {"rostered": "2", "captured_sl": "1 of 2", "sl_total": "4 (from 1 of 2)", "games": "4",
                         "no_games": "0"}
    assert c["theirs"] == {"rostered": "2", "captured_sl": "2 of 2", "sl_total": "8", "games": "4", "no_games": "0"}
    assert c["direct_meetings"] == "3 games · our players 2-1"
    assert c["opponents_met"] == "1 of 2"
    assert c["pairings"] == "1 direct · 1 shared-opponent only · 2 no verified evidence (4 total)"
    empty = team_comparison(ours, theirs, build_pair_index([]), "EIGHT")
    assert empty["direct_meetings"] == "No verified direct meetings between these rosters in this snapshot"


def test_matchup_evidence_orders_opponents_like_the_roster():
    ours = [_m(1, "Ann")]
    theirs = [_m(51, "Pip", sl=3), _m(50, "Opal", sl=5), _m(52, "Quin", sl=None)]
    ev = matchup_evidence(ours, theirs, build_pair_index([]), "EIGHT")
    assert [b["opponent"]["name"] for b in ev["opponents"]] == ["Opal", "Pip", "Quin"]
    assert sorted(theirs, key=member_order_key)[-1]["name"] == "Quin"  # missing SL last


def test_fixture_scope_pairs_are_directed_and_skip_unresolved_opponents():
    match_day = {
        "fixtures": [{"format": "EIGHT"}, {"format": "NINE"}],
        "schedule": {
            "A|d|S": [{"fixture_index": 0, "opponent": {"status": "resolved", "scope_key": "B|d|S"}},
                      {"fixture_index": 1, "opponent": {"status": "bye", "scope_key": None}}],
            "B|d|S": [{"fixture_index": 0, "opponent": {"status": "resolved", "scope_key": "A|d|S"}}],
            "C|d|S": [{"fixture_index": 1, "opponent": {"status": "ambiguous", "scope_key": None}}],
        },
    }
    assert fixture_scope_pairs(match_day) == [("A|d|S", "B|d|S", "EIGHT"), ("B|d|S", "A|d|S", "EIGHT")]


def test_shared_opponent_candidates_are_not_ordered_by_our_record_alone():
    """GPT audit (PR #85): ours 1-0 / opponent 10-0 must not outrank ours 9-1 / opponent 0-10.
    Indirect candidates form one unordered group in roster order; both records stay visible."""
    ours = [_m(1, "Ann"), _m(2, "Bea")]
    rows = [(1, 70, 1, 1), (50, 70, 10, 10)]          # Ann 1-0 vs shared 70; Opal 10-0 vs 70
    rows += [(2, 71, 9, 10), (50, 71, 0, 10)]         # Bea 9-1 vs shared 71; Opal 0-10 vs 71
    ranked = rank_vs_opponent(ours, OPP, build_pair_index(_pairs(*rows)), "EIGHT")["rows"]
    assert [(r["player"].split(" (")[0], r["rank"]) for r in ranked] == [("Ann", "≈"), ("Bea", "≈")]
    assert "theirs 10-0" in ranked[0]["shared_text"] and "theirs 0-10" in ranked[1]["shared_text"]
    assert all("not ordered against other indirect candidates" in r["basis"] for r in ranked)
    assert not any("Tied with" in r["basis"] for r in ranked)
