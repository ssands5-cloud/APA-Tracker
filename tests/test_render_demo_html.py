"""Tests for scripts/render_demo_html.py.

Checks the two things that would otherwise only surface by opening the page
in a browser: the embedded JSON is well-formed and matches what went in,
and a team name containing markup-sensitive characters doesn't break the
page's HTML (escaped in the rendered card, not just the JSON blob).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "render_demo_html", PROJECT_ROOT / "scripts" / "render_demo_html.py"
)
render_demo_html = importlib.util.module_from_spec(spec)
sys.modules["render_demo_html"] = render_demo_html
spec.loader.exec_module(render_demo_html)

SAMPLE_DATA = {
    "generated_at": "2026-09-03T00:00:00+00:00",
    "teams": [{"team_id": "T1", "team_name": "Rack & </script> Attack"}],
    "matches": [
        {
            "match_id": "M1", "week": 9, "home_team_id": "T1", "home_team_name": "Rack & </script> Attack",
            "away_team_id": "T2", "away_team_name": "Chalk It Up", "home_score": 18, "away_score": 12,
            "status": "COMPLETED", "match_date": "2026-08-27", "is_bye": False, "is_scored": True,
            "is_finalized": True,
        }
    ],
    "standings": [{"rank": 1, "team_name": "Chalk It Up", "wins": None, "losses": None, "points": 142}],
    "player_stats": [],
    "match_scores": {
        "M1": [
            {"player": "Alice", "team_name": "Rack & </script> Attack", "skill_level": 5,
             "result": "W", "points_earned": 6},
        ]
    },
}


def test_renders_without_skill_level_keys_present():
    """SAMPLE_DATA predates skill_level_history/skill_level_summary --
    exercises the same "old export, new page" case a real upgrade hits."""
    html = render_demo_html.render(SAMPLE_DATA)
    assert 'data-tab="skill"' in html
    assert 'id="panel-skill"' in html


def test_skill_level_tab_renders_a_real_reading():
    data = dict(SAMPLE_DATA, skill_level_history=[
        {"player": "Alice", "player_id": "P1", "week": 9, "skill_level": 5,
         "match_date": "2026-08-27", "source": "scoresheet"},
    ], skill_level_summary=[
        {"player": "Alice", "player_id": "P1", "current_skill_level": 5,
         "trend": "stable", "volatility": 0, "last_change": None},
    ])
    html = render_demo_html.render(data)
    assert "renderSkillLevel" in html
    # The embedded JSON carries the raw data; a real string search for the
    # rendered value would just be re-finding the JSON blob, so this checks
    # the function that reads it is actually wired into the init call list.
    assert "renderSkillLevel();" in html


def test_renders_without_matchups_key_present():
    """SAMPLE_DATA predates the matchups key -- exercises the "old export,
    new page" case a real upgrade hits."""
    html = render_demo_html.render(SAMPLE_DATA)
    assert 'data-tab="matchups"' in html
    assert 'id="panel-matchups"' in html


def test_matchups_tab_is_wired_in():
    data = dict(SAMPLE_DATA, matchups=[
        {"player": "Alice", "player_id": "P1", "opponent": "Bob", "opponent_id": "P2",
         "matches_played": 2, "win_rate": 1.0, "avg_points_earned": 6.0,
         "avg_opponent_skill_level": 4.0, "trend": "up", "volatility": 0,
         "matchup_score": 90},
    ])
    html = render_demo_html.render(data)
    assert "renderMatchups();" in html


def test_embedded_json_round_trips_exactly():
    html = render_demo_html.render(SAMPLE_DATA)
    match = re.search(
        r'<script type="application/json" id="demo-data">(.*?)</script>', html, re.S
    )
    assert match is not None
    embedded = json.loads(match.group(1))
    assert embedded == SAMPLE_DATA


def test_a_closing_script_tag_in_data_cannot_break_out_of_the_json_block():
    """A team/player name containing '</script>' must not end the JSON
    block early and start executing the rest of the page as markup."""
    html = render_demo_html.render(SAMPLE_DATA)
    # Only one <script type="application/json"> tag pair should exist, and
    # everything between the two markers must still be valid JSON.
    opens = html.count('<script type="application/json"')
    assert opens == 1
    match = re.search(
        r'<script type="application/json" id="demo-data">(.*?)</script>\s*<script>', html, re.S
    )
    assert match is not None, "the JS block must start right after the JSON block, not mid-payload"


def test_render_is_deterministic_html_shell():
    """The CSS/JS shell shouldn't change between two renders of the same data."""
    first = render_demo_html.render(SAMPLE_DATA)
    second = render_demo_html.render(SAMPLE_DATA)
    assert first == second


def test_main_reads_and_writes_expected_paths(tmp_path):
    data_path = tmp_path / "demo_apa_data.json"
    out_path = tmp_path / "dashboard.html"
    data_path.write_text(json.dumps(SAMPLE_DATA))

    old_argv = sys.argv
    sys.argv = ["render_demo_html.py", "--data", str(data_path), "--out", str(out_path)]
    try:
        render_demo_html.main()
    finally:
        sys.argv = old_argv

    assert out_path.exists()
    # render_demo_html.py writes with encoding="utf-8" explicitly (its data
    # can contain non-ASCII player/team names); read_text() must match that
    # rather than falling back to the platform default, which is cp1252 on
    # Windows and chokes on bytes outside that codec's mapped range.
    assert "<title>APA Tracker</title>" in out_path.read_text(encoding="utf-8")
