from __future__ import annotations

from bs4 import BeautifulSoup

from scraper.player_scraper import _extract_match_history

PLAYER_PAGE_HTML = """
<html>
  <body>
    <nav>
      <table>
        <tr><th>Home</th><th>Teams</th><th>Standings</th></tr>
        <tr><td>League</td><td>North</td><td>2nd</td></tr>
      </table>
    </nav>

    <div class="summary">
      <table>
        <tr><th>Won</th><th>Played</th><th>PPM</th></tr>
        <tr><td>42</td><td>60</td><td>2.1</td></tr>
      </table>
    </div>

    <table>
      <thead>
        <tr><th>Date</th><th>Opponent</th><th>Result</th></tr>
      </thead>
      <tbody>
        <tr><td>2024-01-05</td><td>Aces</td><td>W</td></tr>
        <tr><td>2024-01-12</td><td>Rockets</td><td>L</td></tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_match_history_only_reads_qualified_tables():
    soup = BeautifulSoup(PLAYER_PAGE_HTML, "html.parser")
    matches = _extract_match_history(soup)
    assert matches == [
        {"match_date": "2024-01-05", "opponent": "Aces", "result": "W", "skill_level": None, "points_earned": None},
        {"match_date": "2024-01-12", "opponent": "Rockets", "result": "L", "skill_level": None, "points_earned": None},
    ]


def test_no_match_table_returns_empty_list():
    soup = BeautifulSoup("<html><body><table><tr><td>Only</td><td>dummy</td><td>cells</td></tr></table></body></html>", "html.parser")
    assert _extract_match_history(soup) == []
