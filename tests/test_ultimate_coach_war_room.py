"""Unit tests for analytics.ultimate_coach_war_room (Captain's War Room data)."""

from __future__ import annotations

from analytics.ultimate_coach_matchup_evidence import build_pair_index
from analytics.ultimate_coach_war_room import (
    blind_send,
    lineup_budget,
    live_threats,
    quick_read_badges,
    send_cost,
    CATEGORY_LABELS,
    build_local_date,
    category,
    cell_text,
    default_matchup,
    explanation,
    filter_codes,
    freshness,
    meetings_index,
    best_send_text,
    next_send,
    send_labels,
    send_list_text,
    next_send_lines,
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
    assert cell_text(_row()) == "No verified evidence"
    assert explanation(_row(direct=(2, 3), shared=4, ours=(6, 9), theirs=(5, 9))) == (
        "Direct: 2-1 in 3 meetings · Indirect: 4 shared opponents — ours 6-3 (9 games), theirs 5-4 (9 games)")
    assert explanation(_row()) == "No verified direct meetings in this snapshot · no shared opponents"


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
        "Ann vs Opal: 0-3 direct (3 meetings)"]
    opal, pip, quin = wr["cards"]
    assert opal["vs_ours"] == "4-2 in 6 meetings with 2 of our 3 players"
    assert opal["met_list"] == "vs Ann: 3-0 · vs Bea: 1-2"
    assert [t["opponent"]["name"] for t in wr["threats"]] == ["Opal"]
    assert wr["threats"][0]["threat_text"] == (
        "Opal · SL 6 · 4-2 vs our roster (6 meetings, 2 of our players)")
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
             "status": "COMPLETED", "home_score": 9, "away_score": 6},
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


def test_freshness_ignores_a_completed_flag_with_no_real_score_evidence():
    """GPT audit 7a4f8b5 follow-up (2026-10-09 06:12 UTC): the refresh
    engine's diff() was fixed to require real score evidence for its own
    latest-scored-date, but this is the SEPARATE function the actual
    HTML/Excel freshness banner reads from -- it still selected by
    is_scored alone, so a rebuild from the already-fixed refresh engine
    still advertised the wrong date here. APA can flag a fixture
    is_scored=True/COMPLETED with null home/away scores (a scheduling-
    system artifact, not a real result, confirmed live on match 51775357)."""
    match_day = {
        "fixtures": [
            {"local_date": "2026-10-07", "is_scored": True, "status": "COMPLETED",
             "home_score": 9, "away_score": 6},
            {"local_date": "2026-10-12", "is_scored": True, "status": "COMPLETED",
             "home_score": None, "away_score": None},
        ],
    }
    fresh = freshness(match_day, "2026-10-08")
    assert fresh["latest_result"] == "Wed Oct 7, 2026"


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


def test_reason_states_the_evidence_and_its_sample_size_only():
    from analytics.ultimate_coach_war_room import reason
    assert reason({"direct": (2, 2)}) == "2-0 direct record (2 meetings) — favorable · small sample"
    assert reason({"direct": (0, 1)}) == "0-1 direct record (1 meeting) — concerning · small sample"
    assert reason({"direct": (1, 2)}) == "1-1 direct record (2 meetings) — even · small sample"
    assert reason({"direct": None, "shared_count": 1, "ours": (1, 1), "theirs": (0, 1)}) == (
        "shared-opponent results only: ours 1-0 vs theirs 0-1 across 1 shared opponent (no verified direct meetings in this snapshot)")
    assert reason({"direct": None, "shared_count": 0}) == "no recorded evidence"


def test_next_send_ranks_ordered_direct_candidates_and_lists_avoid_and_unknown():
    wr = _war_room()
    opal = next_send(wr, 0)
    assert [(m["medal"], m["display"]) for m in opal["ranked"]] == [("🥇", "Bea")]
    assert opal["headline"] == "First by recorded direct results: Bea"
    # Names here never carry the APA record ID (NAME-DISPLAY-01) -- that's Players-tab-only text.
    assert [a["display"] for a in opal["avoid"]] == ["Ann"] and opal["unknown"] == ["Cal"]
    pip = next_send(wr, 1)                  # an even direct record is ranked; shared-only is never medalled
    assert [(m["medal"], m["display"], m["category"]) for m in pip["ranked"]] == [("🥇", "Cal", "E")]
    assert [u["display"] for u in pip["unordered"]] == ["Bea"]
    assert next_send_lines(pip) == [
        "First by recorded direct results: Cal",
        "1. Cal — 1-1 direct record (2 meetings) — even · small sample",
        # Bea now carries the save warning here: she is our only favorable direct option vs Opal,
        # who has not played. Sending her off this unordered list used to cost that silently.
        "≈ Bea — shared-opponent results only: ours 1-0 vs theirs 1-1 across 1 shared "
        "opponent (no verified direct meetings in this snapshot) · consider saving — our only favorable "
        "direct option vs Opal (2-1 in 3 meetings)",
        "❓ Unknown (no verified evidence, not weak): Ann"]
    quin = next_send(wr, 2)
    assert quin["ranked"] == [] and quin["headline"] == "No evidence-backed option left among our remaining players"
    # Marks: Bea used -> nothing to order vs Opal; Opal played -> says so.
    assert next_send(wr, 0, remaining={1, 3})["ranked"] == []
    used = next_send(wr, 0, unplayed=[False, True, True])          # a used target: no active response at all
    assert used["headline"] == "Opal has already played."
    assert (used["ranked"], used["unordered"], used["avoid"], used["unknown"]) == ([], [], [], [])
    assert next_send_lines(used) == ["Opal has already played."]


def test_next_send_ties_share_a_rank_flags_players_to_save_and_still_lists_the_rest():
    ours = [_m(1, "Ann"), _m(2, "Bo"), _m(3, "Cy"), _m(4, "Di"), _m(5, "Fay")]
    theirs = [_m(50, "Xan"), _m(51, "Yul")]
    index = build_pair_index(_pairs(
        (1, 50, 2, 2), (50, 1, 0, 2), (2, 50, 2, 2), (50, 2, 0, 2),     # Ann, Bo 2-0: tied
        (4, 50, 3, 4), (50, 4, 1, 4), (5, 50, 2, 4), (50, 5, 2, 4),     # Di 3-1, Fay 2-2
        (3, 50, 1, 2), (50, 3, 1, 2),                                   # Cy 1-1 (fourth group)
        (1, 51, 1, 1), (51, 1, 0, 1),                                   # Ann is our only favorable vs Yul
    ))
    wr = war_room_pair(ours, theirs, index, "EIGHT")
    ns = next_send(wr, 0)
    # Cy (fourth group) used to be hidden behind "+1 more"; SEND-LAYOUT-01 gives it its own
    # numbered line (no medal past the top three) instead of a collapse.
    assert [(m["medal"], m["rank"], m["display"]) for m in ns["ranked"]] == [
        ("🥇", "1=", "Ann"), ("🥇", "1=", "Bo"), ("🥈", "3", "Di"), ("🥉", "4", "Fay"), ("", "5", "Cy")]
    assert ns["ranked"][0]["tied_with"] == ["Bo"] and ns["headline"] == "First by recorded direct results: Ann or Bo (tied)"
    assert ns["ranked"][0]["save"] == "consider saving — our only favorable direct option vs Yul (1-0 in 1 meeting, small sample)"
    assert [m["choice_number"] for m in ns["ranked"]] == [1, 1, 2, 3, 4]
    assert "4. Cy — 1-1 direct record (2 meetings) — even · small sample" in next_send_lines(ns)
    assert next_send(wr, 0, unplayed=[True, False])["ranked"][0]["save"] == ""   # Yul already played
    assert next_send(wr, 0, remaining={1, 3, 4, 5})["ranked"][0]["tied_with"] == []


def test_send_labels_number_by_evidence_group_and_never_number_shared_only():
    ours = [_m(1, "Ann"), _m(2, "Bo"), _m(3, "Cy"), _m(4, "Di"), _m(5, "Fay")]
    theirs = [_m(50, "Xan"), _m(51, "Yul")]
    index = build_pair_index(_pairs(
        (1, 50, 2, 2), (50, 1, 0, 2), (2, 50, 2, 2), (50, 2, 0, 2),     # Ann, Bo 2-0: tied
        (4, 50, 3, 4), (50, 4, 1, 4), (5, 50, 2, 4), (50, 5, 2, 4),     # Di 3-1, Fay 2-2
        (3, 50, 1, 2), (50, 3, 1, 2),
        (1, 70, 1, 1), (51, 70, 0, 1), (2, 71, 1, 1), (51, 71, 1, 1),   # Ann, Bo: shared-only vs Yul
    ))
    wr = war_room_pair(ours, theirs, index, "EIGHT")
    xan = [r for r in wr["blocks"][0]["rows"] if r["category"] in ("G", "E", "I")]
    assert send_labels(xan) == ["1=", "1=", "2.", "3.", "4."]
    assert send_list_text(xan).startswith("1= Ann — 2-0 (2) · 1= Bo — 2-0 (2) · 2. Di")
    assert best_send_text(xan).startswith("first by recorded direct results (tied with 1 other, same evidence): Ann")
    assert best_send_text([r for r in xan if r["member"]["id"] != 2]).startswith("first by recorded direct results: Ann")
    yul = [r for r in wr["blocks"][1]["rows"] if r["category"] in ("G", "E", "I")]
    assert send_labels(yul) == ["≈", "≈"]
    assert best_send_text(yul).startswith("shared-opponent candidate, not ordered (one of 2): ")
    assert best_send_text(yul[:1]).startswith("shared-opponent candidate, not ordered (the only one): ")
    assert best_send_text([]) == "" and send_list_text([]) == ""


class TestExcludedEvidenceDisclosure:
    """GPT 7e67f60: a no-evidence cell must not claim nothing was ever played.

    A pairing can have real recorded meetings that this snapshot excluded
    because their identities are unresolved, so the wording has to be about
    what is verified here. And because category() reads the sign of whatever
    subtotal survived, excluded rows can move a label either way -- the note
    must not describe the omission as conservative.
    """

    def test_a_no_evidence_cell_says_verified_rather_than_none(self):
        from analytics.ultimate_coach_war_room import cell_text, explanation

        empty = {"direct": None, "ours": (0, 0), "theirs": (0, 0), "shared_count": 0}

        assert cell_text(empty) == "No verified evidence"
        assert "No verified direct meetings in this snapshot" in explanation(empty)
        # the old wording asserted a fact about history, not about this snapshot
        assert cell_text(empty) != "No evidence"
        assert "No direct meetings ·" not in explanation(empty)

    def test_excluded_evidence_can_flip_a_category_either_way(self):
        """The exact counterexample from the audit, as an executable guard."""
        from analytics.ultimate_coach_war_room import category

        verified_only = {"direct": (1, 1), "ours": (0, 0), "theirs": (0, 0), "shared_count": 0}
        with_excluded = {"direct": (1, 3), "ours": (0, 0), "theirs": (0, 0), "shared_count": 0}

        assert category(verified_only) == "G"
        assert category(with_excluded) == "R"

    def test_the_limits_note_refuses_to_call_the_omission_conservative(self):
        from analytics.ultimate_coach_war_room import EVIDENCE_LIMITS_NOTE

        assert "either direction" in EVIDENCE_LIMITS_NOTE
        assert "favorable can prove concerning" in EVIDENCE_LIMITS_NOTE
        for forbidden in ("conservative", "understate", "only ever"):
            assert forbidden not in EVIDENCE_LIMITS_NOTE.lower()


class TestEvidenceLimitsReachBothSurfaces:
    """The same note has to reach the HTML reader and the Excel reader."""

    def test_the_html_trust_card_carries_the_note(self):
        from analytics.ultimate_coach_war_room import EVIDENCE_LIMITS_NOTE
        from ui.ultimate_coach import _trust_card

        html = _trust_card({"trust": {"identity_exclusion_count": 4221}})

        assert "What excluded evidence means for a decision" in html
        assert "either direction" in html
        # rendered, not just referenced
        assert EVIDENCE_LIMITS_NOTE[:40] in html

    def test_the_excel_trust_sheet_carries_the_note(self):
        from openpyxl import Workbook

        from ui.export_excel_ultimate_coach import _data_trust_sheet

        wb = Workbook()
        _data_trust_sheet(wb, {"trust": {"identity_exclusion_count": 4221}})

        text = chr(10).join(
            str(cell.value)
            for sheet in wb.worksheets
            for row in sheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
        assert "What excluded evidence means for a decision" in text
        assert "either direction" in text


class TestInternalSheetsAreHidden:
    """A captain should not open this workbook into a 30-tab engine dump.

    The internals have to exist because formulas and data validation point at
    them, so they are hidden rather than removed -- and hidden, not veryHidden,
    so the arithmetic stays auditable from the tab bar.
    """

    def test_build_internals_are_hidden_and_user_sheets_are_not(self):
        from ui.export_excel_ultimate_coach import INTERNAL_SHEETS, SHEET_ORDER

        # the sheets user-facing text sends the reader to must never be hidden
        for name in ("Meetings", "Scouting Cards", "Players", "Player vs Player",
                     "START HERE", "Captain Packet", "Lineup Lab", "War Room"):
            assert name in SHEET_ORDER
            assert name not in INTERNAL_SHEETS

        for name in INTERNAL_SHEETS:
            assert name in SHEET_ORDER, f"{name} is not a real sheet"

    def test_a_built_workbook_hides_exactly_those_sheets(self, tmp_path):
        """Checks the actual built workbook, not just the constant."""
        from tests.test_excel_war_room_formulas import _payload
        from ui.export_excel_ultimate_coach import INTERNAL_SHEETS, build_workbook

        wb = build_workbook(_payload())

        hidden = {ws.title for ws in wb.worksheets if ws.sheet_state != "visible"}
        assert hidden == set(INTERNAL_SHEETS), f"unexpected: {hidden ^ set(INTERNAL_SHEETS)}"
        assert wb.active.title == "START HERE"
        # Excel refuses to open a workbook with no visible sheet
        assert any(ws.sheet_state == "visible" for ws in wb.worksheets)


# ---------------------------------------------------------------------------
# Blind send: "we put up first". Every other recommendation in the product is
# conditioned on knowing who they put up, but in APA the lead alternates, so a
# captain regularly has to choose before seeing their player.
# Design: docs/superpowers/specs/2026-10-11-blind-send-design.md


def test_blind_send_leads_with_the_player_who_has_no_concerning_record_not_the_highest_skill():
    """Maximin: the worst case first, coverage second. Ann is our highest SL and the wrong answer.

    Matrix in this fixture: Ann is concerning vs Opal, Bea favorable vs Opal and shared-only vs
    Pip, Cal even vs Pip. Leading Ann risks handing Opal a game we have already lost 0-3.
    """
    wr = _war_room()
    out = blind_send(wr)
    assert out["member"]["name"] == "Bea", out
    assert out["concerning"] == 0 and out["favorable"] == 1, out
    assert "Ann" not in out["why"], out["why"]


def test_blind_send_ignores_opponents_who_have_already_played():
    """Bea's only favorable record is against Opal, so once Opal has played it stops counting."""
    wr = _war_room()
    out = blind_send(wr, unplayed=[False, True, True])
    assert out["member"]["name"] == "Cal", out        # the only recorded meetings left are Cal's
    assert out["favorable"] == 0, out


def test_blind_send_excludes_players_we_marked_unavailable():
    wr = _war_room()
    keep = {m["id"] for m in wr["ours"] if m["name"] != "Bea"}
    out = blind_send(wr, remaining=keep)
    assert out["member"]["name"] != "Bea", out
    assert all(c["member"]["name"] != "Bea" for c in out["ranked"]), out


def test_blind_send_says_plainly_when_the_recommendation_rests_on_almost_nothing():
    """A pick with no recorded record either way must not read like a confident call.

    Superseded by BLIND-01: this used to name a player and call the pick weak. Naming the first
    player in roster order implies an edge that does not exist, so it now names nobody at all.
    """
    wr = _war_room()
    out = blind_send(wr, unplayed=[False, False, True])   # only Quin left; nobody has evidence vs Quin
    assert out["weak"] is True and out["unranked"] is True, out
    assert out["member"] is None, out
    assert "nothing recorded either way" in out["why"].lower(), out["why"]


def test_blind_send_returns_nothing_to_recommend_when_no_one_is_left():
    wr = _war_room()
    assert blind_send(wr, remaining=set())["member"] is None
    assert blind_send(wr, unplayed=[False, False, False])["member"] is None


# ---------------------------------------------------------------------------
# Lineup budget: APA caps the five players you put up at a total skill level
# (23 in standard 8-Ball). Burn the low numbers early and you can be left unable
# to field a legal five. Nothing in the product checked this.


def test_lineup_budget_says_what_is_left_and_whether_a_legal_five_is_still_possible():
    wr = _war_room()            # Ann SL5, Bea SL4, Cal no SL captured
    out = lineup_budget(wr, cap=23, slots=2, played={})     # Ann 5 + Bea 4 are both captured
    assert out["cap"] == 23 and out["used"] == 0 and out["left"] == 23
    assert out["slots_left"] == 2 and out["cheapest"] == 9
    assert out["feasible"] is True
    # Needing a third slot drags in Cal, whose SL was never captured, so legality becomes
    # UNKNOWN rather than true. Refusing to guess is the point.
    assert lineup_budget(wr, cap=23, slots=3, played={})["feasible"] is None


def test_lineup_budget_subtracts_who_has_already_played():
    wr = _war_room()
    out = lineup_budget(wr, cap=23, slots=3, played={1: 5})      # Ann (SL 5) already up
    assert out["used"] == 5 and out["left"] == 18 and out["slots_left"] == 2


def test_lineup_budget_reports_that_a_legal_lineup_is_no_longer_possible():
    """The trap this exists to catch: the cheapest remaining players still blow the cap."""
    wr = _war_room()
    out = lineup_budget(wr, cap=6, slots=2, played={}, remaining={1, 2})           # Ann 5 + Bea 4 = 9 > 6
    assert out["feasible"] is False
    assert "cannot" in out["note"].lower() or "no legal" in out["note"].lower(), out["note"]


def test_lineup_budget_will_not_guess_a_missing_skill_level():
    """Cal has no captured SL. An unknown must make the answer incomplete, never assumed."""
    wr = _war_room()
    out = lineup_budget(wr, cap=23, slots=3, played={})
    assert out["unknown_sl"] == 1
    assert out["complete"] is False
    assert "without a captured" in out["note"].lower(), out["note"]
    missing = lineup_budget(wr, cap=6, slots=2, played={})
    assert "cannot field" not in missing["note"] and "no lineup cleared" in missing["note"]


def test_lineup_budget_is_inert_until_the_captain_supplies_the_cap():
    """The product never assumes a division rule. No cap entered, no claim made."""
    wr = _war_room()
    out = lineup_budget(wr, cap=None, slots=3, played={})
    assert out["cap"] is None and out["feasible"] is None and out["note"] == ""


def test_lineup_budget_checks_whether_sending_one_player_keeps_a_legal_lineup():
    wr = _war_room()
    ann = next(m for m in wr["ours"] if m["name"] == "Ann")
    ok = lineup_budget(wr, cap=23, slots=2, played={}, sending=ann["id"])
    assert ok["sending_keeps_legal"] is True
    tight = lineup_budget(wr, cap=9, slots=2, played={}, sending=ann["id"])   # 5 then cheapest 4 = 9
    assert tight["sending_keeps_legal"] is True
    blown = lineup_budget(wr, cap=8, slots=2, played={}, sending=ann["id"])   # 5 + 4 = 9 > 8
    assert blown["sending_keeps_legal"] is False


def test_save_warning_reaches_shared_opponent_candidates_not_only_medalled_ones():
    """The moment a captain is most blind is the moment the warning went missing.

    With no direct record against this opponent every candidate shows as "≈ not ordered".
    Picking one off that list can burn the only favorable direct option against an opponent
    still to come, and the "consider saving" flag was attached to medals only -- so in exactly
    that situation the product said nothing.

    Here: Bea is shared-opponent-only against Pip, and she is our ONLY favorable direct record
    against Opal, who has not played yet.
    """
    wr = _war_room()
    pip = next(j for j, b in enumerate(wr["blocks"]) if b["opponent"]["name"] == "Pip")
    ns = next_send(wr, pip)
    bea = next((u for u in ns["unordered"] if u["member"]["name"] == "Bea"), None)
    assert bea is not None, [u["member"]["name"] for u in ns["unordered"]]
    assert bea.get("save"), "sending Bea here costs our only favorable option vs Opal"
    assert "Opal" in bea["save"], bea["save"]


def test_save_warning_is_absent_when_nothing_would_be_given_up():
    """It must not cry wolf: a candidate who is nobody's last favorable option carries no flag."""
    wr = _war_room()
    pip = next(j for j, b in enumerate(wr["blocks"]) if b["opponent"]["name"] == "Pip")
    ns = next_send(wr, pip, unplayed=[False, True, True])   # Opal already played
    for u in ns["unordered"]:
        assert not u.get("save"), (u["member"]["name"], u.get("save"))


# BLIND-01 audit findings (GPT, issue #84): the lead card named an arbitrary player when
# nothing supported anyone, and read "no concerning record" when the truth was "no record".


def test_blind_send_names_nobody_when_no_evidence_supports_any_lead():
    """With nothing recorded either way, naming the first roster player implies an edge.

    The response panel below already says "no evidence-backed option". The lead answer must
    agree instead of contradicting it with an arbitrary name.
    """
    wr = _war_room()
    out = blind_send(wr, unplayed=[False, False, True])    # only Quin left; nobody has any record
    assert out["member"] is None, out
    assert out["unranked"] is True
    assert "nothing recorded either way" in out["why"].lower(), out["why"]


def test_blind_send_states_direct_coverage_so_missing_evidence_is_not_read_as_safety():
    """"No concerning record vs any of 3" is misleading when we only have a record against 1.

    Silence about an opponent is not a clean sheet. The reason must say how much of the field
    we actually have a direct record against.
    """
    wr = _war_room()
    out = blind_send(wr)                                   # Bea: favorable vs Opal, nothing vs Pip/Quin
    assert out["member"]["name"] == "Bea"
    why = out["why"].lower()
    assert "1 of the 3" in why or "1 of 3" in why, out["why"]
    assert "no direct record" in why, out["why"]
    assert "no concerning record vs any of" not in why, out["why"]


def test_blind_send_counts_opponents_we_have_no_direct_record_against():
    wr = _war_room()
    out = blind_send(wr)
    assert out["direct_coverage"] == 1 and out["no_record"] == 2, out


def test_blind_send_will_not_dress_an_unknown_player_up_as_an_even_record():
    """BLIND-01 boundary: a candidate with NO record outranks one with a concerning record.

    Sorting by fewest-concerning puts a player nobody has ever recorded above a player with a
    losing record, so the card named him and described it as "even vs 0 of 2". There is no even
    record there — there is no record at all. Unknown is not evidence of a safer lead, and it
    must not be printed as though it were.
    """
    wr = _war_room()
    keep = {m["id"] for m in wr["ours"] if m["name"] in ("Ann", "Cal")}
    out = blind_send(wr, remaining=keep, unplayed=[True, False, True])
    # Cal has nothing recorded vs Opal or Quin; Ann has a concerning record vs Opal.
    assert out["unranked"] is True, out
    assert out["member"] is None, out
    why = out["why"].lower()
    assert "even vs 0" not in why, out["why"]
    assert "unknown" in why and "not safer" in why, out["why"]
    assert "concerning" in why, out["why"]      # the tradeoff is named, not hidden


def test_blind_send_still_recommends_when_the_leader_actually_has_evidence():
    """The guard must not swallow a genuine recommendation."""
    wr = _war_room()
    out = blind_send(wr)
    assert out["member"] is not None and out["unranked"] is False, out
    assert out["direct_coverage"] >= 1, out


# Next Send: what a send COSTS for the rest of the night. The "consider saving" flag only fires
# in the extreme case -- when a player is our sole favorable option against someone still to
# come. Between that and silence a captain had nothing.


def test_send_cost_reports_coverage_before_and_after_the_send():
    """Sending Bea vs Pip costs our only favorable option against Opal.

    The captain should see the size of that, not just a flag: how many of the other unplayed
    opponents still have a favorable option once this player is spent.
    """
    wr = _war_room()
    pip = next(j for j, b in enumerate(wr["blocks"]) if b["opponent"]["name"] == "Pip")
    bea = next(m for m in wr["ours"] if m["name"] == "Bea")
    cost = send_cost(wr, pip, bea["id"])
    assert cost["others"] == 2                      # Opal and Quin are still unplayed
    assert cost["covered_before"] == 1              # only Opal has a favorable option (Bea)
    assert cost["covered_after"] == 0               # and she is the one being spent
    assert cost["lost"] == ["Opal"], cost


def test_send_cost_is_zero_when_the_player_is_nobody_last_favorable_option():
    wr = _war_room()
    pip = next(j for j, b in enumerate(wr["blocks"]) if b["opponent"]["name"] == "Pip")
    cal = next(m for m in wr["ours"] if m["name"] == "Cal")
    cost = send_cost(wr, pip, cal["id"])
    assert cost["lost"] == [] and cost["covered_after"] == cost["covered_before"], cost


def test_send_cost_ignores_opponents_already_played():
    wr = _war_room()
    pip = next(j for j, b in enumerate(wr["blocks"]) if b["opponent"]["name"] == "Pip")
    bea = next(m for m in wr["ours"] if m["name"] == "Bea")
    cost = send_cost(wr, pip, bea["id"], unplayed=[False, True, True])   # Opal already played
    assert cost["others"] == 1 and cost["lost"] == [], cost


# Threat Panel: "dangerous opponents" sums a win/loss record against our WHOLE roster's
# history, including players who are Unavailable or have already Played. A captain reading
# "dangerous" needs to know whether that danger is still live for the sends still ahead.


def test_live_threats_drops_the_flag_entirely_once_real_live_evidence_says_not_dangerous():
    """GPT audit correction: Opal beat Ann 3-0 (gone) but LOSES to Bea 1-2 (still live).

    The first version of this called Opal "no longer a live risk" here, which is correct in
    conclusion but was reached through a branch that could also fire when the live evidence was
    merely absent, not losing. With Bea still in play we have REAL evidence Opal is not
    currently dangerous (a losing record), which is a clean "not dangerous" rather than an
    "unknown" -- so this must not be flagged at all, live or unknown.
    """
    wr = _war_room()
    ann = next(m for m in wr["ours"] if m["name"] == "Ann")
    live = {m["id"] for m in wr["ours"] if m["id"] != ann["id"]}
    out = live_threats(wr, remaining=live)
    assert all(c["opponent"]["name"] != "Opal" for c in out), out


def test_live_threats_calls_it_unknown_not_cleared_when_every_witness_has_left():
    """GPT audit finding: missing evidence is uncertainty, not safety.

    Opal beat Ann 3-0 and beat Bea's record too in aggregate (4-2 vs our whole roster). If BOTH
    Ann and Bea -- the only two players who have ever met her -- are no longer in tonight's
    lineup, there is ZERO evidence against who is actually left. The first version of this said
    "no longer a live risk", which reads as a clearance the data does not support. It must say
    unknown and keep the historical record visible, not declare the opponent safe.
    """
    wr = _war_room()
    cal = next(m for m in wr["ours"] if m["name"] == "Cal")
    out = live_threats(wr, remaining={cal["id"]})
    opal = next((c for c in out if c["opponent"]["name"] == "Opal"), None)
    assert opal is not None, out
    assert opal["live"] is False and opal["unknown"] is True, opal
    assert "no longer a live risk" not in opal["text"].lower(), opal["text"]
    assert "unknown" in opal["text"].lower() and "not cleared" in opal["text"].lower(), opal["text"]
    assert "historically 4-2" in opal["text"].lower(), opal["text"]
    assert "ann" not in opal["text"].lower(), opal["text"]           # names the record, not the player


def test_live_threats_keeps_a_danger_that_is_still_live():
    """With everyone remaining, Opal's live record (4-2) is still a live threat."""
    wr = _war_room()
    out = live_threats(wr)
    opal = next((c for c in out if c["opponent"]["name"] == "Opal"), None)
    assert opal is not None and opal["live"] is True and opal["unknown"] is False, out
    assert opal["wins"] == 4 and opal["games"] == 6, opal


def test_live_threats_is_empty_when_nothing_is_dangerous_either_way():
    wr = _war_room()
    out = live_threats(wr, remaining=set())
    assert out == []


# Quick Read Scouting Cards: Paul's own spec is an icon and a few words a captain can read
# without stopping -- before the detailed facts below, not another sentence to parse.


def _badge_card(rows, losing_sl="—"):
    """A (card, block) pair with their_games computed the SAME way quick_read's own card-building
    loop does: every row with direct evidence counts, whatever its category. The first version of
    quick_read_badges filtered to G/E only and this is exactly the bug that hid (GPT, d3203ee)."""
    tg = sum(r["direct"][1] for r in rows if r.get("direct"))
    return {"losing_sl": losing_sl, "their_games": tg}, {"rows": rows}


def _badge_row(category, direct=None, shared=0):
    return {"category": category, "direct": direct, "shared_count": shared}


def test_quick_read_states_the_actual_meeting_count_at_three_or_more():
    card, block = _badge_card([_badge_row("G", direct=(3, 4))])
    badges = quick_read_badges(card, block, has_note=True)
    assert badges[0] == "Direct meetings vs roster: 4 meetings", badges


def test_quick_read_flags_a_small_sample_under_three_meetings_without_overclaiming_strength():
    card, block = _badge_card([_badge_row("E", direct=(1, 2))])
    badges = quick_read_badges(card, block, has_note=True)
    assert badges[0] == "⚠ Direct meetings vs roster: 2 meetings (small sample)", badges
    assert "strong" not in badges[0].lower() and "limited" not in badges[0].lower(), badges


def test_quick_read_counts_concerning_records_as_evidence_not_its_absence():
    """GPT audit finding (d3203ee): six synthetic unfavorable direct meetings -- the dense
    sentence shows "Threat: 6-0 (6 meetings)" with three avoid records -- produced "No evidence
    on our roster". R is a real direct game we lost, not an absence of data.
    """
    card, block = _badge_card([_badge_row("R", direct=(0, 2)), _badge_row("R", direct=(0, 2)), _badge_row("R", direct=(0, 2))])
    assert card["their_games"] == 6, card
    badges = quick_read_badges(card, block, has_note=True)
    assert badges[0] == "Direct meetings vs roster: 6 meetings", badges
    assert "no evidence" not in badges[0].lower(), badges


def test_quick_read_falls_back_to_shared_opponent_evidence_when_nothing_direct():
    strong_card, strong_block = _badge_card([_badge_row("I", shared=4), _badge_row("I", shared=3)])
    strong = quick_read_badges(strong_card, strong_block, has_note=True)
    assert strong[0] == "✅ Shared-opponent evidence: 2 players, 7 opponent links", strong

    weak_card, weak_block = _badge_card([_badge_row("I", shared=1)])
    weak = quick_read_badges(weak_card, weak_block, has_note=True)
    assert weak[0] == "⚠ Shared-opponent evidence: 1 player, 1 opponent link (thin)", weak


def test_quick_read_says_plainly_when_there_is_nothing_on_our_roster():
    card, block = _badge_card([_badge_row("X")])
    badges = quick_read_badges(card, block, has_note=True)
    assert badges[0] == "⚠ No evidence on our roster", badges


def test_quick_read_surfaces_a_known_weak_skill_level():
    card, block = _badge_card([_badge_row("G", direct=(3, 4))], losing_sl="SL4 (1-3)")
    badges = quick_read_badges(card, block, has_note=True)
    assert "⚠ Recorded losses vs SL4 (1-3)" in badges, badges


def test_quick_read_flags_missing_coach_observations_but_only_when_actually_missing():
    card, block = _badge_card([_badge_row("G", direct=(3, 4))])
    assert "❓ No coach observations" in quick_read_badges(card, block, has_note=False)
    assert "❓ No coach observations" not in quick_read_badges(card, block, has_note=True)


def test_next_send_one_game_leader_discloses_small_sample_without_reranking():
    ours=[_m(1,"One meeting"),_m(2,"Ten meetings")];theirs=[_m(50,"Opponent")]
    index=build_pair_index(_pairs((1,50,1,1),(50,1,0,1),(2,50,8,10),(50,2,2,10)))
    ns=next_send(war_room_pair(ours,theirs,index,"EIGHT"),0)
    assert [r['member']['id'] for r in ns['ranked']]==[1,2]
    assert 'small sample' in ns['ranked'][0]['reason']
    assert 'small sample' not in ns['ranked'][1]['reason']


def test_quick_read_keeps_pair_sample_caution_for_answer_and_avoid():
    ours=[_m(1,"Ann"),_m(2,"Bea"),_m(3,"Jo")];theirs=[_m(50,"Opponent")]
    index=build_pair_index(_pairs((1,50,1,1),(50,1,0,1),(2,50,8,10),(50,2,2,10),(3,50,0,1),(50,3,1,1)))
    wr=war_room_pair(ours,theirs,index,"EIGHT")
    text=wr['cards'][0]['quick_read']
    assert 'Historical top record: Ann (1-0, small sample)' in text
    assert 'Avoid: Jo (0-1, small sample)' in text
    large=war_room_pair([ours[1]],theirs,index,"EIGHT")['cards'][0]['quick_read']
    assert 'Historical top record: Bea (8-2)' in large
    assert 'small sample' not in large


def test_one_meeting_threat_discloses_thin_history_without_clearing_the_flag():
    wr=war_room_pair([_m(1,'Ann')],[_m(50,'Opponent')],build_pair_index(_pairs((1,50,0,1),(50,1,1,1))),'EIGHT')
    row=live_threats(wr)[0]
    assert row['live'] is True and row['wins']==1 and row['games']==1
    assert 'small sample' in row['text'] and 'small sample' in row['short']
    assert '1 meeting' in row['short']
    assert 'small sample' in wr['threats'][0]['threat_text']
    assert 'small sample' in wr['cards'][0]['quick_read']


def test_next_send_discloses_historical_opponent_sl_without_reranking():
    ours=[_m(1,'Ann',sl=5),_m(2,'Bea',sl=4)];theirs=[_m(50,'Opponent',sl=6)]
    index=build_pair_index(_pairs((1,50,1,1),(50,1,0,1),(2,50,8,10),(50,2,2,10)))
    history={(1,50,'EIGHT'):[{'sort':'2026-09-27','opp_sl':4}]}
    wr=war_room_pair(ours,theirs,index,'EIGHT',meetings=history)
    ns=next_send(wr,0)
    assert [r['member']['id'] for r in ns['ranked']]==[1,2]
    assert 'Meeting opponent SL 4; roster capture SL 6' in ns['ranked'][0]['reason']
    assert 'Meeting opponent SL 4; roster capture SL 6' in wr['cards'][0]['quick_read']


def test_meeting_sl_disclosure_handles_missing_mixed_and_unchanged_capture():
    from analytics.ultimate_coach_war_room import meeting_sl_context
    assert meeting_sl_context([], 6) == ""
    assert meeting_sl_context([{"opp_sl": 6}], 6) == ""
    assert meeting_sl_context([{"opp_sl": None}], 6) == "Meeting opponent SL not captured"
    assert meeting_sl_context([{"opp_sl": 4}, {"opp_sl": 6}, {"opp_sl": None}], 6) == (
        "Meeting opponent SL 4, 6; roster capture SL 6; some meeting SLs not captured")
    assert meeting_sl_context([{"opp_sl": 4}], None) == "Meeting opponent SL 4; roster capture SL not captured"


def test_tied_quick_read_does_not_assign_one_players_meeting_sl_to_the_other():
    ours=[_m(1,"Ann"),_m(2,"Bea")];theirs=[_m(50,"Opponent",sl=6)]
    index=build_pair_index(_pairs((1,50,1,1),(50,1,0,1),(2,50,1,1),(50,2,0,1)))
    history={(1,50,"EIGHT"):[{"sort":"2026-09-27","opp_sl":4}],
             (2,50,"EIGHT"):[{"sort":"2026-09-27","opp_sl":6}]}
    wr=war_room_pair(ours,theirs,index,"EIGHT",meetings=history)
    assert "check each pairing's detail" in wr["cards"][0]["quick_read"]
    assert "roster capture SL 6" in next_send(wr,0)["ranked"][0]["reason"]
    assert "roster capture SL" not in next_send(wr,0)["ranked"][1]["reason"]


def test_meeting_sl_context_treats_nonpositive_and_nonnumeric_levels_as_unknown():
    from analytics.ultimate_coach_war_room import meeting_sl_context
    for sl in (0, -1, "4", "", True, float("inf"), float("nan")):
        assert meeting_sl_context([{"opp_sl": sl}], 6) == "Meeting opponent SL not captured"
    assert meeting_sl_context([{"opp_sl": 4}], 0) == "Meeting opponent SL 4; roster capture SL not captured"


def test_meeting_sl_context_handles_mixed_types_and_normalizes_numeric_display():
    from analytics.ultimate_coach_war_room import meeting_sl_context
    assert meeting_sl_context([{"opp_sl": "4"}, {"opp_sl": 6}], 6) == (
        "Meeting opponent SL 6; roster capture SL 6; some meeting SLs not captured")
    assert meeting_sl_context([{"opp_sl": 4.0}], 6.0) == "Meeting opponent SL 4; roster capture SL 6"
