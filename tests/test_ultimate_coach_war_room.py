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
    assert reason({"direct": (2, 2)}) == "2-0 direct record (2 meetings) — favorable"
    assert reason({"direct": (0, 1)}) == "0-1 direct record (1 meeting) — concerning"
    assert reason({"direct": (1, 2)}) == "1-1 direct record (2 meetings) — even"
    assert reason({"direct": None, "shared_count": 1, "ours": (1, 1), "theirs": (0, 1)}) == (
        "shared-opponent results only: ours 1-0 vs theirs 0-1 across 1 shared opponent (no direct meetings)")
    assert reason({"direct": None, "shared_count": 0}) == "no recorded evidence"


def test_next_send_medals_only_ordered_direct_candidates_and_lists_avoid_and_unknown():
    wr = _war_room()
    opal = next_send(wr, 0)
    assert [(m["medal"], m["member"]["name"]) for m in opal["medals"]] == [("🥇", "Bea")]
    assert opal["headline"] == "Best-supported response: Bea"
    assert [a["member"]["name"] for a in opal["avoid"]] == ["Ann"] and opal["unknown"] == ["Cal (APA record ID 1003)"]
    pip = next_send(wr, 1)                  # an even direct record is ordered; shared-only is never medalled
    assert [(m["medal"], m["member"]["name"], m["category"]) for m in pip["medals"]] == [("🥇", "Cal", "E")]
    assert [u["member"]["name"] for u in pip["unordered"]] == ["Bea"]
    assert next_send_lines(pip) == [
        "Best-supported response: Cal",
        "🥇 Cal (APA record ID 1003) — 1-1 direct record (2 meetings) — even",
        "≈ Bea (APA record ID 1002) — shared-opponent results only: ours 1-0 vs theirs 1-1 across 1 shared "
        "opponent (no direct meetings)",
        "❓ Unknown (no evidence, not weak): Ann (APA record ID 1001)"]
    quin = next_send(wr, 2)
    assert quin["medals"] == [] and quin["headline"] == "No evidence-backed option left among our remaining players"
    # Marks: Bea used -> nothing to order vs Opal; Opal played -> says so.
    assert next_send(wr, 0, remaining={1, 3})["medals"] == []
    used = next_send(wr, 0, unplayed=[False, True, True])          # a used target: no active response at all
    assert used["headline"] == "Opal has already played."
    assert (used["medals"], used["unordered"], used["avoid"], used["unknown"], used["more"]) == ([], [], [], [], 0)
    assert next_send_lines(used) == ["Opal has already played."]


def test_next_send_ties_share_a_medal_flags_players_to_save_and_counts_the_rest():
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
    assert [(m["medal"], m["member"]["name"]) for m in ns["medals"]] == [
        ("🥇", "Ann"), ("🥇", "Bo"), ("🥈", "Di"), ("🥉", "Fay")]
    assert ns["medals"][0]["tied_with"] == ["Bo"] and ns["headline"] == "Best-supported response: Ann or Bo (tied)"
    assert ns["medals"][0]["save"] == "consider saving — our only favorable direct option vs Yul"
    assert ns["more"] == 1 and "+ 1 more direct candidate below the top three" in next_send_lines(ns)
    assert next_send(wr, 0, unplayed=[True, False])["medals"][0]["save"] == ""   # Yul already played
    assert next_send(wr, 0, remaining={1, 3, 4, 5})["medals"][0]["tied_with"] == []


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
    assert send_list_text(xan).startswith("1= Ann (APA record ID 1001) — 2-0 (2) · 1= Bo (APA record ID 1002) — 2-0 (2) · 2. Di")
    assert best_send_text(xan).startswith("best-supported send (tied with 1 other, same evidence): Ann")
    assert best_send_text([r for r in xan if r["member"]["id"] != 2]).startswith("best-supported send: Ann")
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
