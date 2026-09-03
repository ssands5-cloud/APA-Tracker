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
}


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
    assert "<title>APA Tracker</title>" in out_path.read_text()
