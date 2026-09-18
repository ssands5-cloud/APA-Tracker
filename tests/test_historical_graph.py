"""Offline tests for recursive real-id historical graph expansion."""

from __future__ import annotations

import json

import pytest

from scraper import historical_graph as graph


def _seed():
    return {
        "schema": "ultimate-coach-historical-catalog-v1",
        "member_id": "1",
        "aliases": [],
        "sessions": [
            {
                "league_id": "12",
                "league_slug": "test-league",
                "session_id": "200",
                "session_name": "Fall 2026",
            }
        ],
        "divisions": [
            {
                "league_id": "12",
                "league_slug": "test-league",
                "division_id": "500",
                "format": "EIGHT",
                "session_id": "200",
                "session_name": "Fall 2026",
                "catalog_session_id": "200",
                "catalog_session_name": "Fall 2026",
            }
        ],
        "source_limitations": [],
    }


def _write_seed(tmp_path):
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(_seed()), encoding="utf-8")
    return path


def test_member_graph_discovers_real_older_session_and_division(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    output = tmp_path / "expanded.json"
    report = tmp_path / "report.json"

    roster_calls = []

    def fake_roster(config, division_id):
        roster_calls.append(str(division_id))
        member = 111 if str(division_id) == "500" else 222
        return {
            "teams": [
                {
                    "id": 1,
                    "name": "T",
                    "isBye": False,
                    "roster": [
                        {
                            "displayName": "Player",
                            "member": {"id": member},
                            "matchesWon": 1,
                            "matchesPlayed": 2,
                            "skillLevel": 4,
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr(graph, "fetch_division_rosters", fake_roster)
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {
                    "id": member_id + 1000,
                    "formats": ["EIGHT"],
                    "league": {"id": 12, "slug": "test-league"},
                }
            ]
        },
    )

    def fake_sessions(config, alias_id, format_name):
        member_id = alias_id - 1000
        if member_id == 111:
            return {
                "id": alias_id,
                "sessions": [
                    {"id": 200, "name": "Fall 2026"},
                    {"id": 150, "name": "Spring 2025"},
                ],
            }
        return {"id": alias_id, "sessions": [{"id": 150, "name": "Spring 2025"}]}

    monkeypatch.setattr(graph, "fetch_alias_sessions", fake_sessions)
    monkeypatch.setattr(
        graph,
        "fetch_league_divisions",
        lambda config, league_slug, session_id: {
            "id": 12,
            "currentSessionId": 200,
            "divisions": [
                {
                    "id": 400,
                    "name": "Old Division",
                    "format": "EIGHT",
                    "type": "EIGHT",
                    "session": {"id": 150, "name": "Spring 2025"},
                }
            ],
        },
    )

    expanded, result = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=output,
        report_path=report,
    )

    assert expanded["counts"]["sessions"] == 2
    assert expanded["counts"]["divisions"] == 2
    assert {row["session_id"] for row in expanded["sessions"]} == {"150", "200"}
    assert {row["division_id"] for row in expanded["divisions"]} == {"400", "500"}
    assert "400" in roster_calls
    assert result["status"] == "expansion_complete"


def test_alias_must_match_exact_league_and_be_unique(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)

    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [
                {
                    "id": 1,
                    "name": "T",
                    "isBye": False,
                    "roster": [
                        {
                            "displayName": "Player",
                            "member": {"id": 111},
                            "matchesWon": 1,
                            "matchesPlayed": 2,
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 1, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}},
                {"id": 2, "formats": ["NINE"], "league": {"id": 12, "slug": "test-league"}},
            ]
        },
    )

    called = {"sessions": 0}

    def no_sessions(*args, **kwargs):
        called["sessions"] += 1
        return {}

    monkeypatch.setattr(graph, "fetch_alias_sessions", no_sessions)

    expanded, result = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert called["sessions"] == 0
    assert expanded["counts"]["sessions"] == 1
    assert any("expected one exact league alias, found 2" in x for x in result["source_limitations"])


def test_never_guesses_session_ids(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)

    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [
                {
                    "id": 1,
                    "name": "T",
                    "isBye": False,
                    "roster": [
                        {
                            "displayName": "Player",
                            "member": {"id": 111},
                            "matchesWon": 0,
                            "matchesPlayed": 0,
                        }
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 999, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}}
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_alias_sessions",
        lambda config, alias_id, format_name: {
            "id": alias_id,
            "sessions": [{"id": 177, "name": "Real Session"}],
        },
    )

    seen = []

    def fake_divisions(config, slug, session_id):
        seen.append(session_id)
        return {"id": 12, "divisions": []}

    monkeypatch.setattr(graph, "fetch_league_divisions", fake_divisions)

    graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
    )

    assert seen == [177]


def test_resume_rejects_seed_catalog_drift(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    report = tmp_path / "report.json"
    output = tmp_path / "expanded.json"
    output.write_text(
        json.dumps(
            {
                "schema": graph.EXPANDED_SCHEMA,
                "sessions": _seed()["sessions"],
                "divisions": _seed()["divisions"],
                "source_limitations": [],
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        json.dumps(
            {
                "seed_catalog_sha256": "wrong",
                "processed_division_keys": [],
                "processed_member_league_keys": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(graph.HistoryGraphError, match="seed catalog changed"):
        graph.expand_historical_catalog(
            {},
            seed_catalog=_seed(),
            seed_catalog_path=seed_path,
            output_path=output,
            report_path=report,
            resume=True,
        )


def test_zero_historical_roster_is_visible_source_limitation(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(graph, "fetch_division_rosters", lambda config, division_id: {"teams": []})

    expanded, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert expanded["counts"]["divisions"] == 1
    assert any("zero roster teams" in x for x in report["source_limitations"])


def test_roster_entry_id_is_never_used_as_member_id_fallback(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [
                {
                    "id": 1,
                    "name": "T",
                    "isBye": False,
                    "roster": [
                        {
                            "id": 999999,
                            "displayName": "No Canonical Member",
                            "member": None,
                            "matchesWon": 1,
                            "matchesPlayed": 2,
                        }
                    ],
                }
            ]
        },
    )
    called = []

    def should_not_call(config, member_id):
        called.append(member_id)
        return {}

    monkeypatch.setattr(graph, "fetch_formats_by_member_id", should_not_call)

    _, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert called == []
    assert any(
        "lacked a canonical numeric member.id" in item
        for item in report["source_limitations"]
    )


def test_zero_division_session_is_queried_only_once_across_many_members(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [
                {
                    "id": 1,
                    "name": "T",
                    "isBye": False,
                    "roster": [
                        {"member": {"id": 111}, "displayName": "A"},
                        {"member": {"id": 222}, "displayName": "B"},
                    ],
                }
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {
                    "id": member_id + 1000,
                    "formats": ["EIGHT"],
                    "league": {"id": 12, "slug": "test-league"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_alias_sessions",
        lambda config, alias_id, format_name: {
            "id": alias_id,
            "sessions": [
                {"id": 200, "name": "Fall 2026"},
                {"id": 177, "name": "Old Empty"},
            ],
        },
    )
    calls = []

    def fake_divisions(config, slug, session_id):
        calls.append(session_id)
        return {"id": 12, "divisions": []}

    monkeypatch.setattr(graph, "fetch_league_divisions", fake_divisions)

    _, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert calls == [177]
    assert report["counts"]["processed_session_catalogs"] >= 2


def test_resume_requires_expanded_catalog_when_checkpoint_exists(tmp_path):
    seed_path = _write_seed(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "seed_catalog_sha256": graph.sha256_file(seed_path),
                "processed_division_keys": ["test-league|200|500"],
                "processed_member_league_keys": [],
                "processed_session_catalog_keys": ["test-league|200"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(graph.HistoryGraphError, match="expanded catalog is missing"):
        graph.expand_historical_catalog(
            {},
            seed_catalog=_seed(),
            seed_catalog_path=seed_path,
            output_path=tmp_path / "missing-expanded.json",
            report_path=report_path,
            resume=True,
        )
