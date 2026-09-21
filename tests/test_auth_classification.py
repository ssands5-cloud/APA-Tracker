"""Offline tests for the shared scope-denial-vs-token-expiry classification
used by historical_archive.py and player_enrichment.py.

No existing dedicated test file covered this module directly before now --
it was only exercised indirectly through test_historical_archive.py and
test_player_enrichment.py's own end-to-end scenarios. These tests exercise
viewer_session_still_valid/call_with_confirmed_denial_retry directly.
"""

from __future__ import annotations

import pytest

from scraper import auth_classification
from scraper.graphql_scraper import AccessTokenExpired


class TestViewerRevalidationTransientFailure:
    def test_viewer_revalidation_transient_error_falls_back_to_normal_auth_path(self, monkeypatch):
        """A transient/non-auth exception during revalidation (a raw
        network error, GraphQLTransportError, AccessTokenMissing, any
        exception other than AccessTokenExpired) must not escape
        viewer_session_still_valid and must not be treated as proof the
        scope denial is real. The ORIGINAL AccessTokenExpired must
        propagate unchanged -- never ConfirmedScopeDenial."""

        def scope_call():
            raise AccessTokenExpired("original scope failure")

        def flaky_revalidation(config):
            raise ConnectionError("simulated transient network failure")

        monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", flaky_revalidation)

        with pytest.raises(AccessTokenExpired, match="original scope failure"):
            auth_classification.call_with_confirmed_denial_retry({}, scope_call)

    def test_viewer_revalidation_success_still_allows_confirmed_denial_sequence(self, monkeypatch):
        """Unchanged behavior: a genuinely, repeatedly confirmed-valid
        viewer still lets two real AccessTokenExpired failures become a
        real ConfirmedScopeDenial."""
        calls = {"scope": 0}

        def scope_call():
            calls["scope"] += 1
            raise AccessTokenExpired("scope denied")

        monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", lambda config: {"id": 999})

        with pytest.raises(auth_classification.ConfirmedScopeDenial):
            auth_classification.call_with_confirmed_denial_retry({}, scope_call)
        assert calls["scope"] == 2

    def test_second_viewer_revalidation_uncertainty_after_retry_prevents_confirmed_denial(self, monkeypatch):
        """The FIRST revalidation genuinely confirms the viewer is valid,
        but the SECOND revalidation (after the retry's own failure) hits a
        transient, non-auth error rather than confirming or denying
        anything. That uncertainty must not be treated as a confirmed
        denial -- the retry's own AccessTokenExpired must propagate
        unchanged, never ConfirmedScopeDenial."""
        revalidation_calls = {"count": 0}

        def flaky_second_revalidation(config):
            revalidation_calls["count"] += 1
            if revalidation_calls["count"] == 1:
                return {"id": 999}
            raise TimeoutError("simulated transient failure on the second check")

        def scope_call():
            raise AccessTokenExpired("scope denied again")

        monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", flaky_second_revalidation)

        with pytest.raises(AccessTokenExpired, match="scope denied again"):
            auth_classification.call_with_confirmed_denial_retry({}, scope_call)
        assert revalidation_calls["count"] == 2

    def test_genuine_viewer_expiry_still_raises_original_failure(self, monkeypatch):
        """A real, confirmed-dead viewer (AccessTokenExpired on
        revalidation, not some other exception) must still raise the
        ORIGINAL scope failure unchanged, preserving normal reauth
        semantics -- unaffected by this fix."""

        def scope_call():
            raise AccessTokenExpired("scope failure while token is dead")

        def dead_viewer(config):
            raise AccessTokenExpired("token is genuinely dead")

        monkeypatch.setattr(auth_classification, "fetch_dashboard_teams", dead_viewer)

        with pytest.raises(AccessTokenExpired, match="scope failure while token is dead"):
            auth_classification.call_with_confirmed_denial_retry({}, scope_call)
