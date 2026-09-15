"""Tests for ui/tabs/player_vs_player.py.

This module is a REPORTER over analytics.player_vs_player's own output --
these tests build PlayerVsPlayerSummary/GameRecord objects directly (the
same real dataclasses that module produces) and assert the rendered page
never recomputes a number, always shows "No data" for a missing one, and
explicitly discloses the innings/defensive-shot/break-run gap rather than
silently omitting it.
"""

from __future__ import annotations

import json

from analytics.player_vs_player import GameRecord, PlayerVsPlayerSummary
from ui.tabs.player_vs_player import NOT_CAPTURED_NOTE, render


def _game(match_id=1, match_date="2026-08-01", result="W", own=5, opp=4,
          points=2.0, balls=None, fmt="8-Ball Open", session="Fall 2026"):
    return GameRecord(
        match_id=match_id, match_date=match_date, result=result,
        own_skill_level=own, opponent_skill_level=opp,
        points_earned=points, nine_ball_points=balls,
        format=fmt, session_name=session,
    )


def _summary(games=(), **overrides):
    defaults = dict(
        player_id="P1", opponent_id="P2", total_games=len(games),
        wins=sum(1 for g in games if g.result == "W"),
        losses=sum(1 for g in games if g.result == "L"),
        sl_delta=-1.0, reliability=0.25, modeled_win_probability=0.64,
        skill_only_probability=0.60, trend="up", recent_trend="stable",
        next_match_projection=0.64, games=tuple(games),
    )
    defaults.update(overrides)
    return PlayerVsPlayerSummary(**defaults)


class TestHeaderAndStats:
    def test_header_carries_real_names_and_record(self):
        summary = _summary([_game(result="W"), _game(match_id=2, result="L")])
        html = render(summary, "Paul Smith", "Rob Stegall")

        assert "Paul Smith" in html
        assert "Rob Stegall" in html
        assert "1-1" in html

    def test_missing_probability_renders_as_no_data_not_zero(self):
        summary = _summary(modeled_win_probability=None, skill_only_probability=None,
                            next_match_projection=None)
        html = render(summary, "P1", "P2")

        assert html.count("No data") >= 3

    def test_the_not_captured_disclosure_is_always_shown(self):
        summary = _summary()
        html = render(summary, "P1", "P2")

        assert NOT_CAPTURED_NOTE in html
        assert "innings" in html.lower()
        assert "defensive-shot" in html.lower()
        assert "break/run" in html.lower()


class TestNoExternalResources:
    def test_carries_no_external_resources(self):
        summary = _summary([_game()])
        html = render(summary, "P1", "P2")

        assert "http://" not in html
        assert "https://" not in html


class TestGameTable:
    def test_every_real_game_appears_in_the_table(self):
        games = [_game(match_id=i, result="W" if i % 2 else "L") for i in range(5)]
        summary = _summary(games)
        html = render(summary, "P1", "P2")

        for i in range(5):
            assert f">{i}<" in html

    def test_no_games_renders_an_honest_empty_state(self):
        summary = _summary([])
        html = render(summary, "P1", "P2")

        assert "No real games recorded" in html

    def test_a_missing_match_date_shows_no_data_not_a_blank_cell(self):
        summary = _summary([_game(match_date=None)])
        html = render(summary, "P1", "P2")

        assert "No data" in html


class TestTimeline:
    def test_a_marker_exists_for_every_real_game(self):
        games = [_game(match_id=i) for i in range(3)]
        summary = _summary(games)
        html = render(summary, "P1", "P2")

        assert html.count("<circle") == 3

    def test_no_games_is_an_honest_empty_timeline(self):
        summary = _summary([])
        html = render(summary, "P1", "P2")

        assert "No games to show" in html


class TestUntrustedText:
    def test_database_text_cannot_break_out_of_the_embedded_script(self):
        hostile = '</script><img src=x onerror="alert(1)">'
        game = _game(match_id=1, fmt=hostile)
        summary = _summary([game])

        html = render(summary, hostile, "P2")

        assert hostile not in html
        assert "\\u003c/script\\u003e" in html
