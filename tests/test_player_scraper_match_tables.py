"""Match-table identification in scraper/player_scraper.py.

The fixture is the audit's: a player page carrying one real match table plus
two unrelated ones. Against the pre-fix parser it yielded five "matches", four
fabricated -- see apa-ground-truth.html,
https://claude.ai/code/artifact/ee8264ee-ac00-4563-b1c8-08d9e20b3a24
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from scraper.player_scraper import (
    _extract_match_history,
    _looks_like_match_table,
    parse_player_stats,
)

PLAYER_PAGE_HTML = """
<html><body>
  <h1>Alice Smith</h1>
  <table class="site-nav"><tr><td>Home</td><td>Teams</td><td>Standings</td></tr></table>
  <table class="lifetime"><tr><th>Won</th><th>Played</th><th>PPM</th></tr>
                          <tr><td>42</td><td>60</td><td>2.1</td></tr></table>
  <table class="player-stats"><tbody>
    <tr><th>Date</th><th>Opponent</th><th>Result</th><th>SL</th><th>Pts</th></tr>
    <tr><td>08/15/2026</td><td>Rack Attack</td><td>W</td><td>5</td><td>3</td></tr>
    <tr><td>08/22/2026</td><td>Side Pocket</td><td>L</td><td>5</td><td>1</td></tr>
  </tbody></table>
</body></html>"""

NO_TABLES_AT_ALL = "<html><body><p>No matches played yet.</p></body></html>"


def _tables(html):
    return BeautifulSoup(html, "html.parser").find_all("table")


class TestTableIdentification:
    def test_navigation_table_is_rejected(self):
        nav = _tables(PLAYER_PAGE_HTML)[0]
        assert _looks_like_match_table(nav) is False

    def test_summary_widget_is_rejected(self):
        lifetime = _tables(PLAYER_PAGE_HTML)[1]
        assert _looks_like_match_table(lifetime) is False

    def test_real_match_table_is_accepted(self):
        stats = _tables(PLAYER_PAGE_HTML)[2]
        assert _looks_like_match_table(stats) is True

    def test_needs_both_date_and_opponent_headers(self):
        date_only = _tables("<table><tr><th>Date</th><th>Points</th></tr></table>")[0]
        assert _looks_like_match_table(date_only) is False


class TestExtraction:
    def test_only_real_matches_are_returned(self):
        soup = BeautifulSoup(PLAYER_PAGE_HTML, "html.parser")
        matches = _extract_match_history(soup)
        assert len(matches) == 2

    def test_none_of_the_audit_fabrications_survive(self):
        soup = BeautifulSoup(PLAYER_PAGE_HTML, "html.parser")
        dates = {m["match_date"] for m in _extract_match_history(soup)}
        # Every one of these was returned as a match before the fix.
        assert dates.isdisjoint({"Home", "Won", "42", "Date"})
        assert dates == {"08/15/2026", "08/22/2026"}

    def test_header_row_of_a_real_table_is_skipped(self):
        soup = BeautifulSoup(PLAYER_PAGE_HTML, "html.parser")
        opponents = {m["opponent"] for m in _extract_match_history(soup)}
        assert "Opponent" not in opponents

    def test_field_mapping_is_unchanged(self):
        """_parse_match_row was deliberately not touched by this change."""
        soup = BeautifulSoup(PLAYER_PAGE_HTML, "html.parser")
        first = _extract_match_history(soup)[0]
        assert first == {
            "match_date": "08/15/2026",
            "opponent": "Rack Attack",
            "result": "W",
            "skill_level": "5",
            "points_earned": "3",
        }

    def test_page_with_no_tables_yields_nothing(self):
        soup = BeautifulSoup(NO_TABLES_AT_ALL, "html.parser")
        assert _extract_match_history(soup) == []


class TestWarnsRatherThanSilentlyReturningNothing:
    def test_tables_present_but_none_qualify_logs_a_warning(self, caplog):
        html = """<html><body>
          <table><tr><th>Won</th><th>Played</th><th>PPM</th></tr>
                 <tr><td>42</td><td>60</td><td>2.1</td></tr></table>
        </body></html>"""
        soup = BeautifulSoup(html, "html.parser")
        with caplog.at_level("WARNING"):
            assert _extract_match_history(soup) == []
        assert any(
            "none had both a date and an opponent header" in record.getMessage()
            for record in caplog.records
        )


class TestEndToEnd:
    def test_parse_player_stats_returns_only_real_matches(self):
        result = parse_player_stats(PLAYER_PAGE_HTML, "P1")
        assert result["player_id"] == "P1"
        assert len(result["matches"]) == 2
