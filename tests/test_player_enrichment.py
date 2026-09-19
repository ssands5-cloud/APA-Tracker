"""Offline tests for all-player Ultimate Coach enrichment."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from database.engine import create_db_engine
from database.models import Player, PlayerLeagueCareerStats, PlayerTeamHistory
from scraper import auth_classification
from scraper import player_enrichment as enrichment
from scraper.graphql_scraper import AccessTokenExpired


def _config(db_path):
    return {"database": {"path": str(db_path)}}


def _catalog():
    return {
        "schema": "ultimate-coach-historical-catalog-v1",
        "divisions": [
            {
                "division_id": "501",
                "league_id": "12",
                "league_slug": "test-league",
                "catalog_session_name": "Summer 2024",
            }
        ],
    }


def test_catalog_context_index_requires_consistent_league():
    catalog = _catalog()
    catalog["divisions"].append(
        {
            "division_id": "501",
            "league_id": "99",
            "league_slug": "other",
            "catalog_session_name": "Summer 2024",
        }
    )
    try:
        enrichment.catalog_context_index(catalog)
    except enrichment.EnrichmentError as exc:
        assert "more than one league" in str(exc)
    else:
        raise AssertionError("ambiguous league mapping must fail closed")


def test_player_league_contexts_uses_exact_division_and_session(tmp_path):
    engine = create_db_engine(_config(tmp_path / "x.db"))
    try:
        with Session(engine) as db:
            player = Player(external_id="123", name="Player A")
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="9",
                    division_id="501",
                    session_name="Summer 2024",
                    is_current=False,
                )
            )
            db.commit()
            contexts = enrichment.player_league_contexts(db, _catalog())
            assert contexts[player.id] == {("12", "test-league")}
    finally:
        engine.dispose()


def test_enrichment_writes_league_scoped_stats_and_is_idempotent(monkeypatch, tmp_path):
    db_path = tmp_path / "ultimate.db"
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "report.json"
    catalog = _catalog()
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    engine = create_db_engine(_config(db_path))

    monkeypatch.setattr(
        enrichment,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {
                    "id": 700,
                    "formats": ["EIGHT", "NINE"],
                    "league": {"id": 12, "slug": "test-league"},
                }
            ]
        },
    )
    monkeypatch.setattr(
        enrichment,
        "fetch_eight_ball_stats",
        lambda config, alias_id: {
            "id": alias_id,
            "displayName": "Player A",
            "players": [],
            "EightBallStats": [
                {
                    "matchesWon": 20,
                    "matchesPlayed": 40,
                    "CLA": 1,
                    "defensiveShotAvg": 2.4,
                    "matchCountForLastTwoYrs": 30,
                    "lastPlayed": "2026-09-01",
                }
            ],
            "NineBallStats": [],
        },
    )

    try:
        with Session(engine) as db:
            player = Player(external_id="123", name="Player A")
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="9",
                    division_id="501",
                    session_name="Summer 2024",
                    is_current=False,
                )
            )
            db.commit()

            first = enrichment.enrich_all_players(
                {},
                db,
                catalog=catalog,
                catalog_path=catalog_path,
                staging_db=db_path,
                report_path=report_path,
                resume=False,
            )
            second = enrichment.enrich_all_players(
                {},
                db,
                catalog=catalog,
                catalog_path=catalog_path,
                staging_db=db_path,
                report_path=report_path,
                resume=True,
            )

            rows = db.query(PlayerLeagueCareerStats).all()
            assert len(rows) == 1
            assert rows[0].league_id == "12"
            assert rows[0].alias_external_id == "700"
            assert rows[0].format == "EIGHT"
            assert rows[0].matches_played == 40
            assert first["counts"]["league_stat_format_rows_written"] == 1
            assert second["counts"]["league_stat_format_rows_written"] == 1
    finally:
        engine.dispose()


def test_ambiguous_league_alias_is_recorded_not_guessed(monkeypatch, tmp_path):
    db_path = tmp_path / "ultimate.db"
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "report.json"
    catalog = _catalog()
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    engine = create_db_engine(_config(db_path))

    monkeypatch.setattr(
        enrichment,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 700, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}},
                {"id": 701, "formats": ["NINE"], "league": {"id": 12, "slug": "test-league"}},
            ]
        },
    )

    try:
        with Session(engine) as db:
            player = Player(external_id="123", name="Player A")
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="9",
                    division_id="501",
                    session_name="Summer 2024",
                    is_current=False,
                )
            )
            db.commit()

            report = enrichment.enrich_all_players(
                {},
                db,
                catalog=catalog,
                catalog_path=catalog_path,
                staging_db=db_path,
                report_path=report_path,
            )
            assert report["counts"]["unresolved_scopes"] == 1
            assert report["unresolved"][0]["candidate_alias_count"] == 2
            assert db.query(PlayerLeagueCareerStats).count() == 0
    finally:
        engine.dispose()


def test_confirmed_alias_stats_denial_is_recorded_unresolved_not_raised(monkeypatch, tmp_path):
    """Stage 4's own auth-classification gap: a per-alias lifetime-stats
    scope discovered through the historical catalog can be genuinely,
    permanently inaccessible to THIS viewer even though the viewer's own
    token is otherwise valid. Without this fix, fetch_eight_ball_stats had
    ZERO exception handling at all -- any AccessTokenExpired propagated
    straight out of enrich_all_players, uncaught, treating a real per-scope
    denial as a full auth expiry forever. Proves: the call is retried once
    after confirming the SAME token is still viewer-valid, and after BOTH
    attempts fail with a confirmed-valid viewer, the scope is recorded
    unresolved rather than raising."""
    db_path = tmp_path / "ultimate.db"
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "report.json"
    catalog = _catalog()
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    engine = create_db_engine(_config(db_path))

    monkeypatch.setattr(
        enrichment,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 700, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}},
            ]
        },
    )

    stats_calls = {"count": 0}

    def denied_stats(config, alias_id):
        stats_calls["count"] += 1
        raise AccessTokenExpired("alias stats forbidden")

    viewer_calls = {"count": 0}

    def always_valid_viewer(config):
        viewer_calls["count"] += 1
        return {"id": 999}

    monkeypatch.setattr(enrichment, "fetch_eight_ball_stats", denied_stats)
    monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", always_valid_viewer)

    try:
        with Session(engine) as db:
            player = Player(external_id="123", name="Player A")
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="9",
                    division_id="501",
                    session_name="Summer 2024",
                    is_current=False,
                )
            )
            db.commit()

            report = enrichment.enrich_all_players(
                {},
                db,
                catalog=catalog,
                catalog_path=catalog_path,
                staging_db=db_path,
                report_path=report_path,
                resume=False,
            )

            assert stats_calls["count"] == 2, "must retry exactly once"
            assert viewer_calls["count"] == 2, "viewer validity must be checked before AND after the retry"
            assert report["counts"]["unresolved_scopes"] == 1
            assert "confirmed-valid viewer token" in report["unresolved"][0]["reason"]
            assert db.query(PlayerLeagueCareerStats).count() == 0
    finally:
        engine.dispose()


def test_genuine_expiry_during_stage4_retry_still_raises_for_reauth(monkeypatch, tmp_path):
    """The narrower race form: the token can genuinely, globally expire in
    the window between the first viewer revalidation and the retry call
    itself. That must still raise for normal reauth/resume, never be
    silently recorded as a permanent unresolved scope."""
    db_path = tmp_path / "ultimate.db"
    catalog_path = tmp_path / "catalog.json"
    report_path = tmp_path / "report.json"
    catalog = _catalog()
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    engine = create_db_engine(_config(db_path))

    monkeypatch.setattr(
        enrichment,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 700, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}},
            ]
        },
    )

    def denied_stats(config, alias_id):
        raise AccessTokenExpired("expired")

    viewer_calls = {"count": 0}

    def viewer_valid_once_then_dead(config):
        viewer_calls["count"] += 1
        if viewer_calls["count"] == 1:
            return {"id": 999}
        raise AccessTokenExpired("viewer session is dead now")

    monkeypatch.setattr(enrichment, "fetch_eight_ball_stats", denied_stats)
    monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", viewer_valid_once_then_dead)

    try:
        with Session(engine) as db:
            player = Player(external_id="123", name="Player A")
            db.add(player)
            db.flush()
            db.add(
                PlayerTeamHistory(
                    player_id=player.id,
                    team_external_id="9",
                    division_id="501",
                    session_name="Summer 2024",
                    is_current=False,
                )
            )
            db.commit()

            try:
                enrichment.enrich_all_players(
                    {},
                    db,
                    catalog=catalog,
                    catalog_path=catalog_path,
                    staging_db=db_path,
                    report_path=report_path,
                    resume=False,
                )
                raise AssertionError("expected AccessTokenExpired to propagate")
            except AccessTokenExpired:
                pass

            assert viewer_calls["count"] == 2
    finally:
        engine.dispose()
