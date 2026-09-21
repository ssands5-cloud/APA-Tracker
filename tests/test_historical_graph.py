"""Offline tests for recursive real-id historical graph expansion."""

from __future__ import annotations

import json

import pytest

from auth.graphql_client import GraphQLTransportError
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


def test_early_source_limitation_is_persisted_before_later_interruption(monkeypatch, tmp_path):
    seed = _seed()
    second = dict(seed["divisions"][0])
    second["division_id"] = "501"
    seed["divisions"].append(second)
    seed["counts"] = {"aliases": 0, "sessions": 1, "divisions": 2}

    seed_path = tmp_path / "seed.json"
    seed_path.write_text(json.dumps(seed), encoding="utf-8")
    output = tmp_path / "expanded.json"
    report = tmp_path / "report.json"

    def fake_roster(config, division_id):
        if str(division_id) == "500":
            return {"teams": []}
        raise RuntimeError("simulated later interruption")

    monkeypatch.setattr(graph, "fetch_division_rosters", fake_roster)

    with pytest.raises(RuntimeError, match="simulated later interruption"):
        graph.expand_historical_catalog(
            {},
            seed_catalog=seed,
            seed_catalog_path=seed_path,
            output_path=output,
            report_path=report,
        )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    checkpoint = json.loads(report.read_text(encoding="utf-8"))
    assert any("zero roster teams" in x for x in persisted["source_limitations"])
    assert "test-league|200|500" in checkpoint["processed_division_keys"]



def test_member_forbidden_is_scope_limitation_when_same_token_still_has_viewer(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [{
                "id": 1,
                "name": "T",
                "isBye": False,
                "roster": [{"displayName": "Restricted", "member": {"id": 111}}],
            }]
        },
    )

    member_calls = {"count": 0}

    def denied_member(config, member_id):
        member_calls["count"] += 1
        raise graph.AccessTokenExpired("scope request was rejected")

    monkeypatch.setattr(graph, "fetch_formats_by_member_id", denied_member)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})

    expanded, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert expanded["counts"]["divisions"] == 1
    assert report["status"] == "expansion_complete"
    assert report["counts"]["processed_divisions"] == 1
    assert report["counts"]["processed_member_league_scopes"] == 1
    assert any(
        "denied member scope twice with a confirmed-valid viewer token" in item
        for item in report["source_limitations"]
    )
    assert member_calls["count"] == 2, (
        "a single AccessTokenExpired must be retried once (with the same "
        "confirmed-valid token) before being trusted as a real, permanent "
        "denial -- see _call_with_confirmed_denial_retry"
    )


def test_member_auth_failure_still_raises_when_same_token_cannot_validate_viewer(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [{
                "id": 1,
                "name": "T",
                "isBye": False,
                "roster": [{"displayName": "Player", "member": {"id": 111}}],
            }]
        },
    )

    def auth_failure(*args, **kwargs):
        raise graph.AccessTokenExpired("expired")

    monkeypatch.setattr(graph, "fetch_formats_by_member_id", auth_failure)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", auth_failure)

    with pytest.raises(graph.AccessTokenExpired, match="expired"):
        graph.expand_historical_catalog(
            {},
            seed_catalog=_seed(),
            seed_catalog_path=seed_path,
            output_path=tmp_path / "expanded.json",
            report_path=tmp_path / "report.json",
        )


def test_division_roster_forbidden_is_checkpointed_when_viewer_remains_valid(monkeypatch, tmp_path):
    seed_path = _write_seed(tmp_path)

    roster_calls = {"count": 0}

    def denied_roster(config, division_id):
        roster_calls["count"] += 1
        raise graph.AccessTokenExpired("division forbidden")

    monkeypatch.setattr(graph, "fetch_division_rosters", denied_roster)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})

    _, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "expansion_complete"
    assert report["counts"]["processed_divisions"] == 1
    assert any(
        "denied roster scope twice with a confirmed-valid viewer token" in item
        for item in report["source_limitations"]
    )
    assert roster_calls["count"] == 2, (
        "a single AccessTokenExpired must be retried once (with the same "
        "confirmed-valid token) before being trusted as a real, permanent "
        "denial -- see _call_with_confirmed_denial_retry"
    )


def test_transient_scope_denial_recovers_on_retry_without_recording_a_limitation(
    monkeypatch, tmp_path
):
    """The exact defect this fix targets: APA's FORBIDDEN response can be a
    one-off/timing-flaky rejection, not a real denial. If the SAME call
    succeeds on retry (after the SAME token is confirmed still viewer-valid),
    the division must be processed normally -- real roster data discovered,
    NOT permanently checkpointed as an unrecoverable source limitation."""
    seed_path = _write_seed(tmp_path)
    roster_calls = {"count": 0}

    def flaky_then_ok_roster(config, division_id):
        roster_calls["count"] += 1
        if roster_calls["count"] == 1:
            raise graph.AccessTokenExpired("transient rejection")
        return {
            "teams": [{
                "id": 1,
                "name": "T",
                "isBye": False,
                "roster": [{"displayName": "Player", "member": {"id": 111}}],
            }]
        }

    monkeypatch.setattr(graph, "fetch_division_rosters", flaky_then_ok_roster)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {"aliases": []},
    )

    expanded, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert roster_calls["count"] == 2
    assert report["status"] == "expansion_complete"
    assert report["counts"]["processed_divisions"] == 1
    assert not any(
        "denied roster scope" in item for item in report["source_limitations"]
    ), "a recovered retry must never be recorded as a source limitation"
    # Real proof the recovered roster payload was actually used, not discarded:
    # the member-scope loop must have run for the roster's real member id.
    assert report["counts"]["processed_member_league_scopes"] == 1


def test_alias_session_history_forbidden_is_checkpointed_when_viewer_remains_valid(
    monkeypatch, tmp_path
):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [{
                "id": 1,
                "name": "T",
                "isBye": False,
                "roster": [{"displayName": "Player", "member": {"id": 111}}],
            }]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 1111, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}}
            ]
        },
    )

    alias_calls = {"count": 0}

    def denied_alias_sessions(config, alias_id, format_name):
        alias_calls["count"] += 1
        raise graph.AccessTokenExpired("alias session history forbidden")

    monkeypatch.setattr(graph, "fetch_alias_sessions", denied_alias_sessions)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})

    _, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "expansion_complete"
    assert alias_calls["count"] == 2
    assert any(
        "denied session-history scope twice with a confirmed-valid viewer token" in item
        for item in report["source_limitations"]
    )


def test_league_division_catalog_forbidden_is_checkpointed_when_viewer_remains_valid(
    monkeypatch, tmp_path
):
    seed_path = _write_seed(tmp_path)
    monkeypatch.setattr(
        graph,
        "fetch_division_rosters",
        lambda config, division_id: {
            "teams": [{
                "id": 1,
                "name": "T",
                "isBye": False,
                "roster": [{"displayName": "Player", "member": {"id": 111}}],
            }]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_formats_by_member_id",
        lambda config, member_id: {
            "aliases": [
                {"id": 1111, "formats": ["EIGHT"], "league": {"id": 12, "slug": "test-league"}}
            ]
        },
    )
    monkeypatch.setattr(
        graph,
        "fetch_alias_sessions",
        lambda config, alias_id, format_name: {
            "id": alias_id,
            "sessions": [{"id": 150, "name": "Spring 2025"}],
        },
    )

    league_calls = {"count": 0}

    def denied_league_divisions(config, league_slug, session_id):
        league_calls["count"] += 1
        raise graph.AccessTokenExpired("division catalog forbidden")

    monkeypatch.setattr(graph, "fetch_league_divisions", denied_league_divisions)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})

    _, report = graph.expand_historical_catalog(
        {},
        seed_catalog=_seed(),
        seed_catalog_path=seed_path,
        output_path=tmp_path / "expanded.json",
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "expansion_complete"
    assert league_calls["count"] == 2
    assert any(
        "denied division catalog scope twice with a confirmed-valid viewer token" in item
        for item in report["source_limitations"]
    )


def test_genuine_expiry_during_retry_still_raises_for_reauth(monkeypatch, tmp_path):
    """The narrower race an independent reviewer found in the first version
    of the retry fix: the token can genuinely, globally expire in the
    window between the first viewer revalidation and the retry call
    itself. That must still raise for normal reauth/resume -- NOT be
    converted into a permanent _ConfirmedScopeDenial/source limitation --
    because the second failure was never actually confirmed against a
    still-valid viewer.

    Sequence: scoped call #1 fails -> viewer check #1 succeeds -> retry
    fails -> viewer check #2 fails (genuine expiry) -> original
    AccessTokenExpired must propagate; nothing is checkpointed as denied.
    """
    seed_path = _write_seed(tmp_path)

    roster_calls = {"count": 0}

    def fails_twice_roster(config, division_id):
        roster_calls["count"] += 1
        raise graph.AccessTokenExpired("expired")

    viewer_calls = {"count": 0}

    def viewer_valid_once_then_dead(config):
        viewer_calls["count"] += 1
        if viewer_calls["count"] == 1:
            return {"id": 999}
        raise graph.AccessTokenExpired("viewer session is dead now")

    monkeypatch.setattr(graph, "fetch_division_rosters", fails_twice_roster)
    monkeypatch.setattr(graph, "fetch_dashboard_teams", viewer_valid_once_then_dead)

    with pytest.raises(graph.AccessTokenExpired, match="expired"):
        graph.expand_historical_catalog(
            {},
            seed_catalog=_seed(),
            seed_catalog_path=seed_path,
            output_path=tmp_path / "expanded.json",
            report_path=tmp_path / "report.json",
        )

    assert roster_calls["count"] == 2, "must retry exactly once before giving up"
    assert viewer_calls["count"] == 2, (
        "viewer validity must be re-checked after the retry's own failure, "
        "not assumed from the first check"
    )


class TestViewerRevalidationTransientFailure:
    """_call_with_confirmed_denial_retry's safety only holds if
    _viewer_session_still_valid can actually distinguish "confirmed the
    viewer is dead" from "could not confirm anything at all" -- these
    tests exercise that function directly, not through the full
    expand_historical_catalog pipeline."""

    def test_viewer_revalidation_transient_error_falls_back_to_normal_auth_path(self, monkeypatch):
        """A transient/non-auth exception during revalidation (a raw
        network error, GraphQLTransportError, AccessTokenMissing, any
        exception other than AccessTokenExpired) must not escape
        _viewer_session_still_valid and must not be treated as proof the
        scope denial is real. The ORIGINAL AccessTokenExpired must
        propagate unchanged -- never _ConfirmedScopeDenial."""

        def scope_call():
            raise graph.AccessTokenExpired("original scope failure")

        def flaky_revalidation(config):
            raise GraphQLTransportError("simulated transient network failure")

        monkeypatch.setattr(graph, "fetch_dashboard_teams", flaky_revalidation)

        with pytest.raises(graph.AccessTokenExpired, match="original scope failure"):
            graph._call_with_confirmed_denial_retry({}, scope_call)

    def test_viewer_revalidation_success_still_allows_confirmed_denial_sequence(self, monkeypatch):
        """Unchanged behavior: a genuinely, repeatedly confirmed-valid
        viewer still lets two real AccessTokenExpired failures become a
        real _ConfirmedScopeDenial."""
        calls = {"scope": 0}

        def scope_call():
            calls["scope"] += 1
            raise graph.AccessTokenExpired("scope denied")

        monkeypatch.setattr(graph, "fetch_dashboard_teams", lambda config: {"id": 999})

        with pytest.raises(graph._ConfirmedScopeDenial):
            graph._call_with_confirmed_denial_retry({}, scope_call)
        assert calls["scope"] == 2

    def test_second_viewer_revalidation_uncertainty_after_retry_prevents_confirmed_denial(self, monkeypatch):
        """The FIRST revalidation genuinely confirms the viewer is valid,
        but the SECOND revalidation (after the retry's own failure) hits a
        transient, non-auth error rather than confirming or denying
        anything. That uncertainty must not be treated as a confirmed
        denial -- the retry's own AccessTokenExpired must propagate
        unchanged, never _ConfirmedScopeDenial."""
        revalidation_calls = {"count": 0}

        def flaky_second_revalidation(config):
            revalidation_calls["count"] += 1
            if revalidation_calls["count"] == 1:
                return {"id": 999}
            raise GraphQLTransportError("simulated transient failure on the second check")

        def scope_call():
            raise graph.AccessTokenExpired("scope denied again")

        monkeypatch.setattr(graph, "fetch_dashboard_teams", flaky_second_revalidation)

        with pytest.raises(graph.AccessTokenExpired, match="scope denied again"):
            graph._call_with_confirmed_denial_retry({}, scope_call)
        assert revalidation_calls["count"] == 2

    def test_unexpected_programming_defect_is_not_swallowed(self, monkeypatch):
        """A TypeError/AttributeError-shaped bug during revalidation is a
        real programming defect, not a transient auth/network condition --
        it must propagate out of _viewer_session_still_valid and out of
        _call_with_confirmed_denial_retry, never be silently converted into
        'cannot confirm the viewer' (False) the way a genuine transient
        failure is. Swallowing it would hide the bug behind the exact same
        safe-looking behavior as a legitimate transient failure."""

        def scope_call():
            raise graph.AccessTokenExpired("original scope failure")

        def buggy_revalidation(config):
            raise TypeError("simulated real programming defect, not an auth/network failure")

        monkeypatch.setattr(graph, "fetch_dashboard_teams", buggy_revalidation)

        with pytest.raises(TypeError, match="simulated real programming defect"):
            graph._call_with_confirmed_denial_retry({}, scope_call)
