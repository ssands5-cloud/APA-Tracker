"""War Room Python/JS mirror contract tests.

The JavaScript in ui/ultimate_coach_war_room.js mirrors several Python functions from
analytics/ultimate_coach_war_room.py. Any drift between the two would produce different
displays in the HTML artifact vs the Excel/Python artifact for the same evidence.

This file verifies the Python side of the contract. The JS test hook
window.__ucMatchPlan (ui/ultimate_coach_war_room.js:775) exposes the JS engine;
a browser-based test should call it with the same fixtures and assert identical output.

Mirror map (Python -> JS):
  category(row)       -> wrCategory(c)       -- evidence category G/R/E/I/X
  cell_text(row)      -> wrCell(c)            -- matrix cell text
  explanation(row)    -> wrExplain(c)         -- full explanation sentence
  reason(row)         -> wrReason(c)          -- send-list reason phrase
  captain_cell(row)   -> wrCaptainCell(c)     -- icon + record for captain view
  blind_send(...)     -> wrBlindSend(w, plan) -- who to lead with when we go first

The minimax engine mirror:
  match_plan(...)     -> mnMatchPlan(...)     -- the full captain plan
  (cross-check test hook: window.__ucMatchPlan)
"""

from __future__ import annotations

import pytest

from analytics.ultimate_coach_war_room import (
    category,
    cell_text,
    explanation,
    reason,
    captain_cell,
    CAPTAIN_ICON,
)


# ---- helpers ----------------------------------------------------------------

def _direct(w: int, g: int) -> dict:
    """A pairing row with a direct record of w wins in g games."""
    return {"direct": (w, g), "shared_count": 0, "ours": None, "theirs": None}


def _shared(ow: int, og: int, tw: int, tg: int, shared: int) -> dict:
    """A pairing row with shared-opponent evidence only."""
    return {"direct": None, "shared_count": shared,
            "ours": (ow, og), "theirs": (tw, tg)}


def _empty() -> dict:
    """A pairing row with no evidence."""
    return {"direct": None, "shared_count": 0, "ours": None, "theirs": None}


# ---- category() / wrCategory() ----------------------------------------------
# JS rule: if c.direct -> w>l → G, w<l → R, else E; else c.shared → I; else X.

class TestCategory:
    def test_favorable(self):
        assert category(_direct(3, 4)) == "G"

    def test_concerning(self):
        assert category(_direct(1, 4)) == "R"

    def test_even(self):
        assert category(_direct(2, 4)) == "E"

    def test_one_win_one_game_favorable(self):
        assert category(_direct(1, 1)) == "G"

    def test_zero_wins_one_game_concerning(self):
        assert category(_direct(0, 1)) == "R"

    def test_shared_only(self):
        assert category(_shared(3, 5, 2, 5, 2)) == "I"

    def test_no_evidence(self):
        assert category(_empty()) == "X"

    def test_direct_beats_shared(self):
        row = {"direct": (1, 2), "shared_count": 3, "ours": (3, 5), "theirs": (2, 5)}
        assert category(row) == "E"   # direct is even, shared is ignored


# ---- cell_text() / wrCell(c) ------------------------------------------------
# JS: direct -> "W-L (g)"; shared -> "≈ W-L vs W-L (n shared)"; else "No verified evidence"

class TestCellText:
    def test_direct_favorable(self):
        txt = cell_text(_direct(3, 4))
        assert "3" in txt and "1" in txt and "(4)" in txt

    def test_direct_even(self):
        txt = cell_text(_direct(2, 4))
        assert "(4)" in txt

    def test_shared(self):
        row = _shared(3, 5, 2, 5, 2)
        txt = cell_text(row)
        assert "≈" in txt
        assert "2 shared" in txt

    def test_no_evidence(self):
        assert cell_text(_empty()) == "No verified evidence"


# ---- explanation() / wrExplain(c) -------------------------------------------

class TestExplanation:
    def test_direct_only(self):
        txt = explanation(_direct(3, 5))
        assert "Direct:" in txt
        assert "no shared opponents" in txt

    def test_shared_only(self):
        row = _shared(3, 5, 2, 5, 2)
        txt = explanation(row)
        assert "No verified direct meetings" in txt
        assert "Indirect:" in txt
        assert "2 shared opponent" in txt

    def test_both(self):
        row = {"direct": (3, 5), "shared_count": 2, "ours": (3, 5), "theirs": (2, 5)}
        txt = explanation(row)
        assert "Direct:" in txt
        assert "Indirect:" in txt


# ---- reason() / wrReason(c) -------------------------------------------------

class TestReason:
    def test_favorable_direct(self):
        txt = reason(_direct(3, 4))
        assert "favorable" in txt
        assert "direct record" in txt

    def test_concerning_direct(self):
        txt = reason(_direct(1, 4))
        assert "concerning" in txt

    def test_small_sample(self):
        txt = reason(_direct(1, 2))
        assert "small sample" in txt

    def test_shared_only(self):
        txt = reason(_shared(3, 5, 2, 5, 2))
        assert "shared-opponent" in txt
        assert "no verified direct" in txt.lower()

    def test_no_evidence(self):
        txt = reason(_empty())
        assert "no recorded evidence" in txt


# ---- captain_cell() / wrCaptainCell(c) --------------------------------------

class TestCaptainCell:
    def test_favorable_shows_green_icon(self):
        txt = captain_cell(_direct(3, 4))
        assert txt.startswith(CAPTAIN_ICON["G"])

    def test_concerning_shows_red_icon(self):
        txt = captain_cell(_direct(1, 4))
        assert txt.startswith(CAPTAIN_ICON["R"])

    def test_even_shows_yellow_icon(self):
        txt = captain_cell(_direct(2, 4))
        assert txt.startswith(CAPTAIN_ICON["E"])

    def test_shared_shows_approx(self):
        txt = captain_cell(_shared(3, 5, 2, 5, 2))
        assert "≈" in txt

    def test_no_evidence_shows_white_icon(self):
        txt = captain_cell(_empty())
        assert txt.startswith(CAPTAIN_ICON["X"])


# ---- mirror invariants (category drives everything) -------------------------

class TestMirrorInvariants:
    """Cross-cutting rules that must hold in both Python and JS."""

    @pytest.mark.parametrize("w,g,expected", [
        (5, 8, "G"), (3, 8, "R"), (4, 8, "E"),
        (1, 1, "G"), (0, 1, "R"), (0, 0, "E"),  # 0-0 is even (degenerate direct)
    ])
    def test_category_exhaustive(self, w, g, expected):
        assert category(_direct(w, g)) == expected

    def test_category_is_primary_key(self):
        """The same category always drives the same icon."""
        for cat, icon in CAPTAIN_ICON.items():
            if cat == "G":
                row = _direct(1, 1)
            elif cat == "R":
                row = _direct(0, 1)
            elif cat == "E":
                row = _direct(1, 2)
            elif cat == "I":
                row = _shared(1, 2, 1, 2, 1)
            else:
                row = _empty()
            assert category(row) == cat
            assert captain_cell(row).startswith(icon)

    def test_shared_only_reason_never_says_favorable_or_concerning(self):
        """Shared-opponent evidence is unordered: reason must never rank it."""
        txt = reason(_shared(5, 5, 0, 5, 3))
        assert "favorable" not in txt
        assert "concerning" not in txt
