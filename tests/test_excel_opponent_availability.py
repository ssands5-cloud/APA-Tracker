"""Opponent Availability on Lineup Lab (Excel), evaluated without Excel by tests/excel_formula_eval.py.

Rules under test (owner request 2026-11-22; same rule the HTML's opponent "Out" mark already follows):
- every opposing player has an Availability dropdown on Lineup Lab, default Available;
- Played and Unavailable are separate states: a player who played stays Played, whatever else is marked;
- an Unavailable opponent who has not played is out of best sends, risks, threats, plans and Next Send;
- the marks are inputs for ONE fixture and never change historical evidence;
- the V2 macro engine receives the same flag (static wiring check; the native HTML/Excel parity is in
  tests/test_uc_v2_excel_parity.py).
"""
from __future__ import annotations

import re

import pytest
from openpyxl import load_workbook

from tests.excel_formula_eval import Workbook
from tests.test_excel_war_room_formulas import (
    ANN, BEA, CAM, DEE, EVE, LL, OWLS, WR, _list_after, _no_bad_values, _opportunities, _payload, _roster, _row,
)
from ui.excel_v2_coach import ARGS, BAS
from ui.export_excel_ultimate_coach import write_workbook

CAM_AVAIL, EVE_AVAIL = "G23", "G24"      # Lineup Lab opponent Availability, rows follow Played in C23/C24
CAM_PLAYED, EVE_PLAYED = "C23", "C24"
CC = "Command Center"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = write_workbook(_payload(), tmp_path_factory.mktemp("oppav") / "uc.xlsx", built_at="2026-10-07 18:00 UTC",
                          viewer_member_external_id="1001", viewer_card_number="80000001")
    return load_workbook(path)


@pytest.fixture()
def book(built):
    return Workbook(built)


def _named(book, name):
    return book.value("Engine", book.name(name).ref)


def _range(book, name):
    """Values of a multi-cell Engine range name, in order."""
    return [book.value(sheet, ref) for sheet, ref in book.name(name)]


def _out(book):
    return _range(book, "wr_OppOut")[:2]          # Cam, Eve (the fixture's two opponents)


def _played_col(book):
    """War Room opponent roster, 'Played' column, in roster order."""
    _, theirs = _roster(book, WR, 15)
    return [t[3] for t in theirs]


def test_every_opponent_has_an_availability_dropdown_defaulting_to_available(built, book):
    ws = built[LL]
    assert [ws.cell(row=22, column=c).value for c in range(1, 8)] == [
        "#", "Player", "Played", "Coach notes", "SL", "Team W-L", "Availability"]
    rules = [(str(dv.sqref), dv.formula1) for dv in ws.data_validations.dataValidation]
    availability_cells = {c for sq, f in rules if f == '"Available,Unavailable"' for c in sq.split()}
    assert {f"G{r}" for r in range(23, 31)} <= availability_cells        # one per opponent roster row (8 rows)
    assert {f"C{r}" for r in range(23, 31)} <= {c for sq, f in rules if f == '"Played"' for c in sq.split()}
    assert all(ws[f"G{r}"].value is None for r in range(23, 31))          # nothing marked: blank = Available
    assert ws.column_dimensions["G"].width >= 12 and ws.column_dimensions["C"].width == 18   # layout kept elsewhere
    assert _played_col(book) == ["—", "—"]
    assert _out(book) == [False, False] and _range(book, "wr_OppAvail")[:2] == ["Available", "Available"]
    assert _named(book, "wr_UnplayedCount") == 2


def test_unavailable_opponent_is_excluded_from_advice_but_evidence_is_kept(book, built):
    before = _opportunities(book, built)
    book.set(LL, CAM_AVAIL, "Unavailable")
    assert _opportunities(book, built)[0] == (f"vs {CAM} · SL 6", "Marked unavailable.")
    assert _opportunities(book, built)[1] == before[1]                    # Eve's advice is unchanged
    assert _played_col(book) == ["Unavailable", "—"]                      # roster shows the mark, not "Played"
    assert _out(book) == [True, False] and _range(book, "wr_OppUnplayed")[:2] == [False, True]
    assert _named(book, "wr_UnplayedCount") == 1
    risks = _list_after(book, built, "Open risks — unplayed opponents with no favorable direct option left among our remaining players", 8)
    assert risks == [f"{EVE} — only even or indirect evidence left"]      # Cam can no longer be a risk
    unique = _list_after(book, built, "Unique favorable options — consider saving (the only remaining favorable direct option vs an unplayed opponent)", 8)
    assert unique == ["None right now."]
    # historical evidence is untouched: inspecting Cam still shows Ann's real 2-0
    inspect = _row(built, WR, "Inspect opponent")
    book.set(WR, f"C{inspect}", CAM)
    assert [book.display(WR, f"{c}{inspect + 2}") for c in "ACE"] == [ANN, "1", "2-0 (2 meetings)"]
    # clearing the mark restores everything
    book.set(LL, CAM_AVAIL, "")
    assert _opportunities(book, built) == before and _named(book, "wr_UnplayedCount") == 2


def test_played_and_unavailable_stay_separate_states(book, built):
    book.set(LL, CAM_AVAIL, "Unavailable")
    book.set(LL, CAM_PLAYED, "Played")                                    # both marked: he did play
    assert _opportunities(book, built)[0] == (f"vs {CAM} · SL 6", "Already played.")
    assert _played_col(book)[0] == "Played"
    assert _out(book) == [False, False]                                   # a player who played is never "out"
    assert _range(book, "wr_OppPlayed")[0] == "Played" and _range(book, "wr_OppAvail")[0] == "Unavailable"
    assert book.value(LL, CAM_AVAIL) == "Unavailable" and book.value(LL, CAM_PLAYED) == "Played"   # both inputs kept
    book.set(LL, CAM_PLAYED, "")                                          # un-mark Played: Unavailable shows again
    assert _opportunities(book, built)[0] == (f"vs {CAM} · SL 6", "Marked unavailable.")
    assert _played_col(book)[0] == "Unavailable" and _out(book)[0] is True
    book.set(LL, CAM_AVAIL, "")                                           # Played alone is unchanged behavior
    book.set(LL, CAM_PLAYED, "Played")
    assert _opportunities(book, built)[0] == (f"vs {CAM} · SL 6", "Already played.")


def test_several_opponents_absent_at_once(book, built):
    book.set(LL, CAM_AVAIL, "Unavailable")
    book.set(LL, EVE_AVAIL, "Unavailable")
    assert _played_col(book) == ["Unavailable", "Unavailable"] and _out(book) == [True, True]
    assert _named(book, "wr_UnplayedCount") == 0
    assert [o[1] for o in _opportunities(book, built)] == ["Marked unavailable."] * 2
    assert _no_bad_values(book, built) == []                              # an empty candidate list must not error
    book.set(LL, EVE_AVAIL, "")                                           # one comes back
    assert _named(book, "wr_UnplayedCount") == 1
    assert _opportunities(book, built)[0][1] == "Marked unavailable." and _opportunities(book, built)[1][1] != "Marked unavailable."


def test_next_send_says_why_an_unavailable_put_up_gets_no_advice(book):
    book.set(CC, "C6", CAM)
    book.set(LL, CAM_PLAYED, "Played")
    assert _named(book, "wr_NsHeadline") == f"{CAM} has already played (Lineup Lab)."
    book.set(LL, CAM_PLAYED, "")
    book.set(LL, CAM_AVAIL, "Unavailable")
    assert _named(book, "wr_NsHeadline") == f"{CAM} is marked unavailable (Lineup Lab)."


def test_opponent_availability_only_applies_to_the_fixture_it_was_marked_for(book, built):
    book.set(LL, CAM_AVAIL, "Unavailable")
    assert _played_col(book)[0] == "Unavailable"
    book.set(LL, "C6", OWLS)                                              # Lineup Lab now plans another opponent
    assert _played_col(book)[0] == "—"                                    # mark ignored, like Played and our own marks
    assert _opportunities(book, built)[0][1] != "Marked unavailable."


def test_v2_engine_receives_the_opponent_out_flag_in_the_workbook_wiring():
    args = ARGS.split(",")
    assert args[args.index("wr_OppUnplayed") + 1] == "wr_OppOut"
    signature = re.search(r"Public Function UC_V2\((.*?)\) As Variant", BAS.read_text(encoding="utf-8"), re.S)[1]
    params = [p.strip().split(" As ")[0] for p in signature.replace("_\n", "").split(",")]
    assert params[0] == "view" and len(params) == 1 + len(args)           # every workbook argument has a VBA parameter
    assert params[params.index("oppUnplayed") + 1] == "oppOut"
