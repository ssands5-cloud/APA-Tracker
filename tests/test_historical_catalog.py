"""Offline contract tests for the Ultimate Coach historical catalog."""

from __future__ import annotations

from scraper import historical_catalog as catalog
from scraper.graphql_scraper import alias_session_rows, alias_session_team_rows, league_division_rows


def test_alias_session_rows_preserve_real_session_and_format():
    alias = {
        "id": 77,
        "sessions": [
            {"id": 134, "name": "Summer 2024"},
            {"id": 135, "name": "Fall 2024"},
        ],
    }
    assert alias_session_rows(alias, "EIGHT") == [
        {"alias_id": "77", "session_id": "134", "session_name": "Summer 2024", "format": "EIGHT"},
        {"alias_id": "77", "session_id": "135", "session_name": "Fall 2024", "format": "EIGHT"},
    ]


def test_alias_session_team_rows_keep_null_stats_null():
    alias = {
        "id": 77,
        "league": {"id": 12, "slug": "test-league"},
        "players": [
            {
                "__typename": "NineBallPlayer",
                "team": {"id": 991, "name": "Night Owls", "number": "4", "active": True},
                "matchesWon": 3,
                "matchesPlayed": 7,
                "ppm": None,
                "pa": None,
            }
        ],
    }
    row = alias_session_team_rows(alias, 134, "NINE")[0]
    assert row["team_id"] == "991"
    assert row["matches_won"] == 3
    assert row["ppm"] is None
    assert row["pa"] is None


def test_league_division_rows_preserve_source_session():
    league = {
        "id": 12,
        "currentSessionId": 200,
        "divisions": [
            {
                "id": 501,
                "name": "Monday 8",
                "number": "01",
                "format": "EIGHT",
                "type": "EIGHT",
                "nightOfPlay": "MONDAY",
                "isMine": False,
                "session": {"id": 134, "name": "Summer 2024"},
            }
        ],
    }
    row = league_division_rows(league)[0]
    assert row["division_id"] == "501"
    assert row["session_id"] == "134"
    assert row["format"] == "EIGHT"


def test_catalog_deduplicates_session_across_formats_and_fetches_divisions_once(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [{"id": 77, "formats": ["EIGHT", "NINE"], "league": {"id": 12, "slug": "test-league"}}]
        },
    )
    calls = {"sessions": [], "divisions": []}

    def fake_sessions(config, alias_id, format_name):
        calls["sessions"].append((alias_id, format_name))
        return {"id": alias_id, "sessions": [{"id": 134, "name": "Summer 2024"}]}

    def fake_divisions(config, league_slug, session_id):
        calls["divisions"].append((league_slug, session_id))
        return {
            "id": 12,
            "currentSessionId": 200,
            "divisions": [
                {"id": 501, "name": "Monday 8", "format": "EIGHT", "type": "EIGHT", "session": {"id": 134, "name": "Summer 2024"}},
                {"id": 502, "name": "Tuesday 9", "format": "NINE", "type": "NINE", "session": {"id": 134, "name": "Summer 2024"}},
            ],
        }

    monkeypatch.setattr(catalog, "fetch_alias_sessions", fake_sessions)
    monkeypatch.setattr(catalog, "fetch_league_divisions", fake_divisions)

    report = catalog.build_historical_catalog({}, 123)

    assert calls["sessions"] == [(77, "EIGHT"), (77, "NINE")]
    assert calls["divisions"] == [("test-league", 134)]
    assert report["counts"] == {"aliases": 1, "sessions": 1, "divisions": 2}
    assert report["sessions"][0]["formats_discovered"] == ["EIGHT", "NINE"]
    assert {row["division_id"] for row in report["divisions"]} == {"501", "502"}


def test_catalog_records_zero_divisions_as_source_limitation(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [{"id": 77, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}}]
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_alias_sessions",
        lambda config, alias_id, format_name: {"id": alias_id, "sessions": [{"id": 134, "name": "Summer 2024"}]},
    )
    monkeypatch.setattr(
        catalog,
        "fetch_league_divisions",
        lambda config, league_slug, session_id: {"id": 12, "divisions": []},
    )

    report = catalog.build_historical_catalog({}, 123)

    assert report["counts"]["sessions"] == 1
    assert report["counts"]["divisions"] == 0
    assert any("zero divisions" in item for item in report["source_limitations"])


def test_catalog_rejects_division_labeled_with_wrong_session(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [{"id": 77, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}}]
        },
    )
    monkeypatch.setattr(
        catalog,
        "fetch_alias_sessions",
        lambda config, alias_id, format_name: {"id": alias_id, "sessions": [{"id": 134, "name": "Summer 2024"}]},
    )
    monkeypatch.setattr(
        catalog,
        "fetch_league_divisions",
        lambda config, league_slug, session_id: {
            "id": 12,
            "divisions": [{"id": 501, "name": "Wrong Season", "format": "EIGHT", "session": {"id": 999, "name": "Other"}}],
        },
    )

    report = catalog.build_historical_catalog({}, 123)

    assert report["counts"]["divisions"] == 0
    assert any("requested session 134" in item for item in report["source_limitations"])
